"""Idempotent retry capability for failed OIS publication jobs."""
from __future__ import annotations

import json
from typing import Any
from backend.knowledge.contracts import OUTBOX_SCHEMA, entry_ref, outbox_ref
from backend.knowledge.provider import register_capability
from backend.knowledge.ids import new_knowledge_id
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.knowledge.storage import publish_proposal_markdown


def _scope(context, alias: str = "p") -> tuple[str, list[Any]]:
    if context.source == "worker":
        return "1=1", []
    team = context.team_gid or ""
    return (f"({alias}.creator_gid=%s OR (%s <> '' AND {alias}.team_gid=%s))", [context.user_gid, team, team])


def retry_publish(payload: dict[str, Any], context) -> dict[str, Any]:
    outbox_gid = str(payload.get("outbox_gid") or "").strip()
    if not outbox_gid:
        raise ValueError("outbox_gid is required")
    from backend.knowledge.data.connection import get_knowledge_conn as get_conn

    # Phase 1 only claims work. No network/OIS call is allowed while this
    # database transaction is open.
    with get_conn() as conn:
        with conn.cursor() as cur:
            scope, scope_params = _scope(context)
            cur.execute(
                "SELECT o.*, p.title, p.content_md, p.tags, p.creator_gid, p.status AS proposal_status, p.published_gid "
                "FROM workmanship_know_publish_outbox o JOIN workmanship_know_proposals p ON p.gid=o.proposal_gid "
                f"WHERE o.gid=%s AND {scope} FOR UPDATE",
                [outbox_gid, *scope_params],
            )
            row = cur.fetchone()
            if not row:
                raise LookupError("补偿任务不存在或当前用户不可见")
            row = dict(row)
            if row.get("status") == "completed":
                published_gid = row.get("published_gid")
                return {"object_ref": outbox_ref(outbox_gid), "outbox_gid": outbox_gid, "status": "completed", "published_gid": published_gid, "published_ref": entry_ref(published_gid) if published_gid else None, "idempotent": True}
            if row.get("status") == "publishing" and row.get("next_retry_at"):
                cur.execute("SELECT NOW() >= %s AS reclaimable", (row["next_retry_at"],))
                if not bool((cur.fetchone() or {}).get("reclaimable")):
                    raise CapabilityBusinessError(
                        "publication_in_progress",
                        "Knowledge publication is already in progress.",
                        retryable=True,
                    )
            if int(row.get("attempts") or 0) >= 8:
                cur.execute("UPDATE workmanship_know_publish_outbox SET status='dead', updated_at=NOW() WHERE gid=%s", (outbox_gid,))
                conn.commit()
                return {"object_ref": outbox_ref(outbox_gid), "outbox_gid": outbox_gid, "status": "dead", "idempotent": False}

            proposal_gid = row["proposal_gid"]
            cur.execute("SELECT gid, content_ref FROM workmanship_know_entries WHERE source_gid=%s LIMIT 1", (proposal_gid,))
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE workmanship_know_proposals SET status='approved', published_gid=%s, updated_at=NOW() WHERE gid=%s",
                    (existing["gid"], proposal_gid),
                )
                cur.execute("UPDATE workmanship_know_publish_outbox SET status='completed', updated_at=NOW() WHERE gid=%s", (outbox_gid,))
                conn.commit()
                return {"object_ref": outbox_ref(outbox_gid), "outbox_gid": outbox_gid, "status": "completed", "published_gid": existing["gid"], "published_ref": entry_ref(existing["gid"]), "idempotent": True}
            cur.execute(
                "UPDATE workmanship_know_publish_outbox SET status='publishing',attempts=attempts+1,"
                "next_retry_at=DATE_ADD(NOW(),INTERVAL 5 MINUTE),last_error=NULL,updated_at=NOW() WHERE gid=%s",
                (outbox_gid,),
            )
        conn.commit()

    content_md = str(row.get("content_md") or "")
    proposal_gid = str(row["proposal_gid"])
    try:
        publication = publish_proposal_markdown(proposal_gid, content_md)
    except Exception as exc:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_know_publish_outbox SET status='pending',last_error=%s,"
                    "next_retry_at=DATE_ADD(NOW(),INTERVAL LEAST(3600,POW(2,attempts)*60) SECOND),"
                    "updated_at=NOW() WHERE gid=%s AND status='publishing'",
                    ("Knowledge object storage unavailable", outbox_gid),
                )
            conn.commit()
        raise CapabilityBusinessError(
            "knowledge_storage_unavailable",
            "Knowledge object storage is unavailable; publication remains retryable.",
            retryable=True,
        ) from exc

    # Phase 2 finalizes metadata atomically after the immutable object exists.
    with get_conn() as conn:
        with conn.cursor() as cur:
            scope, scope_params = _scope(context)
            cur.execute(
                "SELECT o.status,o.proposal_gid,p.title,p.content_md,p.tags,p.creator_gid,p.published_gid "
                "FROM workmanship_know_publish_outbox o JOIN workmanship_know_proposals p ON p.gid=o.proposal_gid "
                f"WHERE o.gid=%s AND {scope} FOR UPDATE",
                [outbox_gid, *scope_params],
            )
            current = cur.fetchone()
            if not current:
                raise LookupError("补偿任务不存在或当前用户不可见")
            current = dict(current)
            if current.get("status") == "completed":
                return {"object_ref": outbox_ref(outbox_gid), "outbox_gid": outbox_gid, "status": "completed", "published_gid": current.get("published_gid"), "published_ref": entry_ref(current["published_gid"]) if current.get("published_gid") else None, "idempotent": True}
            cur.execute("SELECT gid FROM workmanship_know_entries WHERE source_gid=%s LIMIT 1 FOR UPDATE", (proposal_gid,))
            existing = cur.fetchone()
            published_gid = str(existing["gid"]) if existing else new_knowledge_id("entry")
            tags = current.get("tags") or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except (TypeError, ValueError):
                    tags = []
            content_ref = json.dumps({
                "ois_url": publication["ois_url"], "object_key": publication["object_key"],
                "proposal_gid": proposal_gid, "sha256": publication["sha256"],
            }, ensure_ascii=False)
            if not existing:
                cur.execute(
                    """INSERT INTO workmanship_know_entries
                       (gid, display_id, title, entry_type, content_ref, content_md, tags,
                        status, share_scope, creator_gid, source_gid, source_label, created_at, updated_at)
                       VALUES (%s, '', %s, 'guide', %s, %s, %s, 'published', 'team', %s, %s,
                               'knowledge.proposal', NOW(), NOW())""",
                    (published_gid, current.get("title") or "", content_ref, content_md, json.dumps(tags, ensure_ascii=False), current.get("creator_gid") or context.user_gid, proposal_gid),
                )
            cur.execute(
                "UPDATE workmanship_know_proposals SET status='approved',published_gid=%s,ois_url=%s,updated_at=NOW() WHERE gid=%s",
                (published_gid, publication["ois_url"], proposal_gid),
            )
            cur.execute("UPDATE workmanship_know_publish_outbox SET status='completed',last_error=NULL,updated_at=NOW() WHERE gid=%s", (outbox_gid,))
        conn.commit()
    return {"object_ref": outbox_ref(outbox_gid), "outbox_gid": outbox_gid, "status": "completed", "published_gid": published_gid, "published_ref": entry_ref(published_gid), "sha256": publication["sha256"], "idempotent": bool(existing)}


def register_retry_capability(registry) -> None:
    from .models_next import CapabilitySpec
    register_capability(registry, CapabilitySpec(owner="knowledge",
        id="knowledge.proposal.outbox.retry", version=1,
        description="重试一个 OIS 知识发布补偿任务，幂等创建正式知识条目。",
        risk="write", confirmation="user", permissions=("knowledge.manage",),
        input_schema={"type": "object", "required": ["outbox_gid"], "properties": {"outbox_gid": {"type": "string"}}},
        output_schema=OUTBOX_SCHEMA, idempotent=True, tags=("knowledge", "review", "operations", "write"),
    ), retry_publish)
