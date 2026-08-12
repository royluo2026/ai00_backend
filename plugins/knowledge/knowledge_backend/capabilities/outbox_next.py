"""Team-scoped outbox primitives for reliable OIS publication retries."""
from __future__ import annotations
import json
from typing import Any
from plugins.knowledge.knowledge_backend.contracts import OUTBOX_LIST_SCHEMA, outbox_ref, proposal_ref, transport_value
from plugins.knowledge.knowledge_backend.provider import register_capability

def enqueue_publish(proposal_gid: str, payload: dict[str, Any], *, gid: str, error: str) -> None:
    from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn as get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO workmanship_know_publish_outbox
                (gid, proposal_gid, payload, status, attempts, last_error, created_at, updated_at)
                VALUES (%s, %s, %s, 'pending', 0, %s, NOW(), NOW())""",
                        (gid, proposal_gid, json.dumps(payload, ensure_ascii=False), error))
        conn.commit()

def list_outbox(payload: dict[str, Any], context) -> dict[str, Any]:
    limit = max(1, min(int(payload.get("limit") or 50), 200))
    team = context.team_gid or ""
    from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn as get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT o.gid, o.proposal_gid, o.status, o.attempts, o.next_retry_at, o.last_error, o.created_at, o.updated_at "
                "FROM workmanship_know_publish_outbox o "
                "JOIN workmanship_know_proposals p ON p.gid=o.proposal_gid "
                "WHERE p.creator_gid=%s OR (%s <> '' AND p.team_gid=%s) "
                "ORDER BY o.updated_at DESC LIMIT %s",
                (context.user_gid, team, team, limit),
            )
            rows = cur.fetchall()
    return {
        "items": [
            {
                **transport_value(dict(row)),
                "object_ref": outbox_ref(row["gid"]),
                "proposal_ref": proposal_ref(row["proposal_gid"]),
            }
            for row in rows
        ],
        "total": len(rows),
    }

def register_outbox_capability(registry) -> None:
    from backend.capability_v2.provider_contracts import CapabilitySpec
    register_capability(registry, CapabilitySpec(owner="knowledge",
        id="knowledge.proposal.outbox.list", version=1,
        description="查看当前用户或团队可见的知识发布补偿队列。",
        permissions=("knowledge.manage",),
        plugin_callable=True,
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
        output_schema=OUTBOX_LIST_SCHEMA, tags=("knowledge", "review", "operations"),
    ), list_outbox)

def mark_complete(gid: str) -> None:
    from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn as get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE workmanship_know_publish_outbox SET status='completed', updated_at=NOW() WHERE gid=%s", (gid,))
        conn.commit()
