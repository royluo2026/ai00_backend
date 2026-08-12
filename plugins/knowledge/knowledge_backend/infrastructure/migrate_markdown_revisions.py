#!/usr/bin/env python3
"""Knowledge-owned migration from legacy markdown to immutable revisions."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.knowledge.revision_store import (
    canonical_markdown,
    load_markdown_revision,
    prepare_markdown_revision,
    store_markdown_revision,
)


@dataclass(frozen=True)
class LegacyRevisionPlan:
    entry_gid: str
    document_gid: str
    revision_gid: str
    slug: str


def plan_legacy_revision(entry_gid: str, markdown: str) -> LegacyRevisionPlan:
    source = str(entry_gid or "").strip()
    if not source:
        raise ValueError("entry_gid is required")
    entry_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]
    content_hash = hashlib.sha256(canonical_markdown(markdown).encode("utf-8")).hexdigest()[:24]
    return LegacyRevisionPlan(
        entry_gid=source,
        document_gid=f"legacy-doc-{entry_hash}",
        revision_gid=f"legacy-rev-{content_hash}",
        slug=f"legacy-{entry_hash}",
    )


def inventory(conn, limit: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT gid,title,content_md,creator_gid,share_scope FROM workmanship_know_entries "
            "WHERE content_md IS NOT NULL AND content_md<>'' ORDER BY gid LIMIT %s",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def inventory_summary(rows: list[dict]) -> dict:
    return {
        "entries": len(rows),
        "bytes": sum(
            len(canonical_markdown(str(row.get("content_md") or "")).encode("utf-8"))
            for row in rows
        ),
    }


def partition_inventory(
    rows: list[dict], tenant_gid: str, user_summaries: dict[str, dict],
) -> dict[str, list[dict]]:
    tenant = str(tenant_gid or "").strip()
    if not tenant:
        raise ValueError("tenant_gid is required")
    eligible: list[dict] = []
    quarantined: list[dict] = []
    other_tenant: list[dict] = []
    for row in rows:
        creator_gid = str(row.get("creator_gid") or "")
        creator = user_summaries.get(creator_gid)
        creator_team = str((creator or {}).get("team_id") or "")
        if not creator_gid or not creator or not creator_team:
            quarantined.append(row)
        elif creator_team != tenant:
            other_tenant.append(row)
        elif str(row.get("share_scope") or "team") in {"local", "team"}:
            eligible.append(row)
        else:
            quarantined.append(row)
    return {
        "eligible": eligible,
        "quarantined": quarantined,
        "other_tenant": other_tenant,
    }

def _source_sha256(markdown: str) -> str:
    return hashlib.sha256(canonical_markdown(markdown).encode("utf-8")).hexdigest()


def create_migration_run(
    conn, rows: list[dict], *, tenant_gid: str, space_gid: str, actor_gid: str,
) -> str:
    from backend.platform_sdk.ids import next_gid

    run_gid = str(next_gid())
    summary = inventory_summary(rows)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO workmanship_know_migration_runs "
            "(gid,tenant_gid,space_gid,actor_gid,status,source_count,source_bytes,started_at) "
            "VALUES (%s,%s,%s,%s,'running',%s,%s,NOW())",
            (run_gid, tenant_gid, space_gid, actor_gid, summary["entries"], summary["bytes"]),
        )
    conn.commit()
    return run_gid


def _record_item(
    conn, *, run_gid: str, plan: LegacyRevisionPlan, markdown: str, status: str,
    source_sha256: str | None = None, object_key: str | None = None,
    content_sha256: str | None = None, error_message: str | None = None,
) -> None:
    source_digest = source_sha256 or _source_sha256(markdown)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO workmanship_know_migration_items "
            "(run_gid,entry_gid,document_gid,revision_gid,status,source_sha256,object_key,content_sha256,error_message,started_at,finished_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),CASE WHEN %s='running' THEN NULL ELSE NOW() END) "
            "ON DUPLICATE KEY UPDATE status=VALUES(status),object_key=VALUES(object_key),"
            "content_sha256=VALUES(content_sha256),error_message=VALUES(error_message),"
            "finished_at=VALUES(finished_at),updated_at=NOW()",
            (
                run_gid, plan.entry_gid, plan.document_gid, plan.revision_gid, status,
                source_digest, object_key, content_sha256,
                (error_message or "")[:4000] or None, status,
            ),
        )
    conn.commit()


def _finish_run(conn, run_gid: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status,COUNT(*) AS n FROM workmanship_know_migration_items "
            "WHERE run_gid=%s GROUP BY status",
            (run_gid,),
        )
        counts = {str(row["status"]): int(row["n"]) for row in cur.fetchall()}
        failed = counts.get("failed", 0)
        cur.execute(
            "UPDATE workmanship_know_migration_runs SET status=%s,copied_count=%s,skipped_count=%s,"
            "failed_count=%s,verified_count=%s,finished_at=NOW(),updated_at=NOW() WHERE gid=%s",
            (
                "failed" if failed else "completed",
                counts.get("copied", 0) + counts.get("verified", 0),
                counts.get("skipped", 0), failed, counts.get("verified", 0), run_gid,
            ),
        )
    conn.commit()
    return {
        "run_gid": run_gid,
        "copied": counts.get("copied", 0) + counts.get("verified", 0),
        "skipped": counts.get("skipped", 0),
        "failed": failed,
        "verified": counts.get("verified", 0),
        "source_retained": True,
    }


def fail_migration_run(conn, run_gid: str, error: Exception) -> dict:
    message = f"{type(error).__name__}: {error}"[:4000]
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE workmanship_know_migration_runs SET status='failed',last_error=%s,"
            "failed_count=CASE WHEN failed_count=0 THEN 1 ELSE failed_count END,"
            "finished_at=NOW(),updated_at=NOW() WHERE gid=%s",
            (message, run_gid),
        )
    conn.commit()
    return {
        "run_gid": run_gid,
        "copied": 0,
        "skipped": 0,
        "failed": 1,
        "verified": 0,
        "source_retained": True,
        "error": message,
    }

def migrate_rows(
    conn, rows: list[dict], *, tenant_gid: str, space_gid: str, actor_gid: str,
    run_gid: str | None = None,
) -> dict:
    copied = skipped = failed = 0
    with conn.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO workmanship_know_spaces "
            "(gid,tenant_gid,name,visibility,created_by) VALUES (%s,%s,%s,'team',%s)",
            (space_gid, tenant_gid, "迁移知识空间", actor_gid),
        )
    conn.commit()
    for row in rows:
        markdown = str(row.get("content_md") or "")
        plan = plan_legacy_revision(row["gid"], markdown)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid FROM workmanship_know_documents WHERE source_entry_gid=%s LIMIT 1",
                (plan.entry_gid,),
            )
            if cur.fetchone():
                skipped += 1
                if run_gid:
                    _record_item(conn, run_gid=run_gid, plan=plan, markdown=markdown, status="skipped")
                continue
        if run_gid:
            _record_item(conn, run_gid=run_gid, plan=plan, markdown=markdown, status="running")
        prepared = prepare_markdown_revision(
            tenant_gid=tenant_gid,
            space_gid=space_gid,
            document_gid=plan.document_gid,
            revision_gid=plan.revision_gid,
            markdown=markdown,
        )
        stored = None
        try:
            stored = store_markdown_revision(prepared)
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_know_documents "
                    "(gid,tenant_gid,space_gid,title,slug,status,current_revision_gid,published_revision_gid,source_entry_gid,created_by) "
                    "VALUES (%s,%s,%s,%s,%s,'published',%s,%s,%s,%s)",
                    (
                        plan.document_gid, tenant_gid, space_gid,
                        row.get("title") or "未命名知识", plan.slug,
                        plan.revision_gid, plan.revision_gid, plan.entry_gid,
                        row.get("creator_gid") or actor_gid,
                    ),
                )
                cur.execute(
                    "INSERT INTO workmanship_know_revisions "
                    "(gid,tenant_gid,space_gid,document_gid,revision_no,object_key,content_sha256,byte_size,media_type,state,created_by) "
                    "VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s,'published',%s)",
                    (
                        plan.revision_gid, tenant_gid, space_gid, plan.document_gid,
                        stored["object_key"], stored["sha256"], stored["byte_size"],
                        stored["media_type"], row.get("creator_gid") or actor_gid,
                    ),
                )
                creator_gid = row.get("creator_gid") or actor_gid
                cur.execute(
                    "INSERT INTO workmanship_know_document_acl "
                    "(document_gid,subject_type,subject_gid,permission,created_by) "
                    "VALUES (%s,'user',%s,'admin',%s)",
                    (plan.document_gid, creator_gid, actor_gid),
                )
                if str(row.get("share_scope") or "team") == "team":
                    cur.execute(
                        "INSERT INTO workmanship_know_document_acl "
                        "(document_gid,subject_type,subject_gid,permission,created_by) "
                        "VALUES (%s,'team',%s,'edit',%s)",
                        (plan.document_gid, tenant_gid, actor_gid),
                    )
            conn.commit()
            copied += 1
            if run_gid:
                _record_item(
                    conn, run_gid=run_gid, plan=plan, markdown=markdown, status="copied",
                    object_key=stored["object_key"], content_sha256=stored["sha256"],
                )
        except Exception as exc:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid FROM workmanship_know_documents WHERE source_entry_gid=%s LIMIT 1",
                    (plan.entry_gid,),
                )
                concurrently_completed = bool(cur.fetchone())
            if concurrently_completed:
                skipped += 1
                status, error = "skipped", None
            else:
                failed += 1
                status = "failed"
                error = f"{type(exc).__name__}: {exc}"
            if run_gid:
                _record_item(
                    conn, run_gid=run_gid, plan=plan, markdown=markdown, status=status,
                    object_key=stored.get("object_key") if stored else None,
                    content_sha256=stored.get("sha256") if stored else None,
                    error_message=error,
                )
    if run_gid:
        return _finish_run(conn, run_gid)
    return {"copied": copied, "skipped": skipped, "failed": failed, "source_retained": True}


def verify_migration_run(conn, run_gid: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT entry_gid,document_gid,revision_gid,source_sha256,object_key,content_sha256 "
            "FROM workmanship_know_migration_items WHERE run_gid=%s AND status='copied' ORDER BY entry_gid",
            (run_gid,),
        )
        items = [dict(row) for row in cur.fetchall()]
        cur.execute(
            "UPDATE workmanship_know_migration_runs SET status='verifying',finished_at=NULL,updated_at=NOW() WHERE gid=%s",
            (run_gid,),
        )
    conn.commit()
    for item in items:
        plan = LegacyRevisionPlan(
            str(item["entry_gid"]), str(item["document_gid"]), str(item["revision_gid"]), "",
        )
        try:
            markdown = load_markdown_revision(item["object_key"], item["content_sha256"])
            if _source_sha256(markdown) != item["source_sha256"]:
                raise RuntimeError("source and OIS digest do not match")
            _record_item(
                conn, run_gid=run_gid, plan=plan, markdown=markdown,
                source_sha256=item["source_sha256"], status="verified",
                object_key=item["object_key"], content_sha256=item["content_sha256"],
            )
        except Exception as exc:
            _record_item(
                conn, run_gid=run_gid, plan=plan, markdown="",
                source_sha256=item["source_sha256"], status="failed",
                object_key=item.get("object_key"), content_sha256=item.get("content_sha256"),
                error_message=f"verification {type(exc).__name__}: {exc}",
            )
    return _finish_run(conn, run_gid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-gid", required=True)
    parser.add_argument("--space-gid", required=True)
    parser.add_argument("--actor-gid", required=True)
    parser.add_argument("--limit", type=int, default=1000, help="Maximum eligible rows to migrate")
    parser.add_argument("--scan-limit", type=int, default=10000, help="Maximum legacy rows to inventory")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from plugins.knowledge.knowledge_backend.data.connection import (
        get_knowledge_conn as get_conn,
    )
    from backend.platform_sdk.identity import get_user_summaries
    with get_conn() as conn:
        scanned = inventory(conn, max(1, min(args.scan_limit, 100000)))
        creators = get_user_summaries(row.get("creator_gid") for row in scanned)
        partitioned = partition_inventory(scanned, args.tenant_gid, creators)
        rows = partitioned["eligible"][:max(1, min(args.limit, 10000))]
        print(json.dumps({
            **inventory_summary(rows),
            "scanned": len(scanned),
            "eligible_total": len(partitioned["eligible"]),
            "selected": len(rows),
            "quarantined": len(partitioned["quarantined"]),
            "other_tenant": len(partitioned["other_tenant"]),
            "apply": args.apply,
            "source_retained": True,
        }, ensure_ascii=False))
        if not args.apply:
            return 0
        run_gid = create_migration_run(
            conn, rows, tenant_gid=args.tenant_gid, space_gid=args.space_gid, actor_gid=args.actor_gid,
        )
        try:
            result = migrate_rows(
                conn, rows, tenant_gid=args.tenant_gid, space_gid=args.space_gid,
                actor_gid=args.actor_gid, run_gid=run_gid,
            )
            result = verify_migration_run(conn, run_gid)
        except Exception as exc:
            conn.rollback()
            result = fail_migration_run(conn, run_gid, exc)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
