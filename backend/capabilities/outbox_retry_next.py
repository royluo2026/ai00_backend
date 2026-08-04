"""Idempotent retry capability for failed OIS publication jobs."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _scope(context, alias: str = "p") -> tuple[str, list[Any]]:
    if context.source == "worker":
        return "1=1", []
    team = context.team_gid or ""
    return (f"({alias}.creator_gid=%s OR (%s <> '' AND {alias}.team_gid=%s))", [context.user_gid, team, team])


def retry_publish(payload: dict[str, Any], context) -> dict[str, Any]:
    outbox_gid = str(payload.get("outbox_gid") or "").strip()
    if not outbox_gid:
        raise ValueError("outbox_gid is required")
    from backend.db.connection import get_conn
    from backend.utils.gid import next_gid

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
                return {"outbox_gid": outbox_gid, "status": "completed", "idempotent": True}
            if int(row.get("attempts") or 0) >= 8:
                cur.execute("UPDATE workmanship_know_publish_outbox SET status='dead', updated_at=NOW() WHERE gid=%s", (outbox_gid,))
                conn.commit()
                return {"outbox_gid": outbox_gid, "status": "dead", "idempotent": False}

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
                return {"outbox_gid": outbox_gid, "status": "completed", "published_gid": existing["gid"], "idempotent": True}

            content_md = str(row.get("content_md") or "")
            content_sha256 = hashlib.sha256(content_md.encode("utf-8")).hexdigest()
            from backend.core.ois_storage import upload
            ois_url = upload(content_md.encode("utf-8"), ".md", "text/markdown", prefix="knowledge")
            if not ois_url:
                cur.execute("UPDATE workmanship_know_publish_outbox SET attempts=attempts+1, last_error=%s, next_retry_at=DATE_ADD(NOW(), INTERVAL LEAST(3600, POW(2, attempts) * 60) SECOND), updated_at=NOW() WHERE gid=%s", ("OIS unavailable", outbox_gid))
                conn.commit()
                raise RuntimeError("OIS 不可用，补偿任务保留 pending")

            published_gid = str(next_gid())
            tags = row.get("tags") or []
            if isinstance(tags, str):
                try: tags = json.loads(tags)
                except (TypeError, ValueError): tags = []
            content_ref = json.dumps({"ois_url": ois_url, "proposal_gid": proposal_gid, "sha256": content_sha256}, ensure_ascii=False)
            cur.execute(
                """INSERT INTO workmanship_know_entries
                   (gid, display_id, title, entry_type, content_ref, content_md, tags,
                    status, share_scope, creator_gid, source_gid, source_label, created_at, updated_at)
                   VALUES (%s, '', %s, 'guide', %s, %s, %s, 'published', 'team', %s, %s,
                           'knowledge.proposal', NOW(), NOW())""",
                (published_gid, row.get("title") or "", content_ref, content_md, json.dumps(tags, ensure_ascii=False), row.get("creator_gid") or context.user_gid, proposal_gid),
            )
            cur.execute("UPDATE workmanship_know_proposals SET status='approved', published_gid=%s, ois_url=%s, updated_at=NOW() WHERE gid=%s", (published_gid, ois_url, proposal_gid))
            cur.execute("UPDATE workmanship_know_publish_outbox SET status='completed', attempts=attempts+1, last_error=NULL, updated_at=NOW() WHERE gid=%s", (outbox_gid,))
        conn.commit()
    return {"outbox_gid": outbox_gid, "status": "completed", "published_gid": published_gid, "sha256": content_sha256, "idempotent": False}


def register_retry_capability(registry) -> None:
    from .models_next import CapabilitySpec
    registry.register(CapabilitySpec(
        id="knowledge.proposal.outbox.retry", version=1,
        description="重试一个 OIS 知识发布补偿任务，幂等创建正式知识条目。",
        risk="write", confirmation="user", permissions=("knowledge.manage",),
        input_schema={"type": "object", "required": ["outbox_gid"], "properties": {"outbox_gid": {"type": "string"}}},
        output_schema={"type": "object"}, idempotent=True, tags=("knowledge", "review", "operations", "write"),
    ), retry_publish)
