"""Review queue read capabilities for knowledge proposals."""
from __future__ import annotations

import json
from typing import Any
from backend.knowledge.contracts import PROPOSAL_LIST_SCHEMA, PROPOSAL_SCHEMA, entry_ref, proposal_ref, transport_value
from backend.knowledge.provider import register_capability


def _scope(context, alias: str = "p") -> tuple[str, list[Any]]:
    team = context.team_gid or ""
    return (
        f"({alias}.creator_gid = %s OR (%s <> '' AND {alias}.team_gid = %s))",
        [context.user_gid, team, team],
    )


def list_proposals(payload: dict[str, Any], context) -> dict[str, Any]:
    status = str(payload.get("status") or "pending").strip()
    limit = max(1, min(int(payload.get("limit") or 50), 200))
    allowed = {"pending", "publishing", "approved", "rejected"}
    if status not in allowed:
        raise ValueError("status must be pending, publishing, approved or rejected")
    from backend.knowledge.data.connection import get_knowledge_conn as get_conn
    scope, params = _scope(context)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, base_gid, title, summary, tags, status, creator_gid, team_gid, "
                "reviewer_gid, reviewed_at, published_gid, ois_url, created_at, updated_at "
                f"FROM workmanship_know_proposals p WHERE p.status=%s AND {scope} "
                "ORDER BY p.updated_at DESC LIMIT %s",
                [status, *params, limit],
            )
            rows = cur.fetchall()
    items = []
    for row in rows:
        item = transport_value(dict(row))
        item["summary"] = str(item.get("summary") or "")
        if isinstance(item.get("tags"), str):
            try:
                item["tags"] = json.loads(item["tags"])
            except (TypeError, ValueError):
                item["tags"] = []
        item["tags"] = [str(value) for value in (item.get("tags") or [])]
        item["object_ref"] = proposal_ref(item["gid"])
        item["published_ref"] = entry_ref(item["published_gid"]) if item.get("published_gid") else None
        items.append(item)
    return {"items": items, "total": len(items), "status": status}


def get_proposal(payload: dict[str, Any], context) -> dict[str, Any]:
    proposal_gid = str(payload.get("proposal_gid") or "").strip()
    if not proposal_gid:
        raise ValueError("proposal_gid is required")
    from backend.knowledge.data.connection import get_knowledge_conn as get_conn
    scope, params = _scope(context)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM workmanship_know_proposals p WHERE p.gid=%s AND {scope}",
                [proposal_gid, *params],
            )
            row = cur.fetchone()
    if not row:
        raise LookupError("知识提案不存在或当前用户不可见")
    result = transport_value(dict(row))
    result["summary"] = str(result.get("summary") or "")
    result["object_ref"] = proposal_ref(result["gid"])
    result["published_ref"] = entry_ref(result["published_gid"]) if result.get("published_gid") else None
    if isinstance(result.get("tags"), str):
        try:
            result["tags"] = json.loads(result["tags"])
        except (TypeError, ValueError):
            result["tags"] = []
    result["tags"] = [str(value) for value in (result.get("tags") or [])]
    return result


def register_proposal_query_capabilities(registry) -> None:
    from .models_next import CapabilitySpec

    register_capability(registry,
        CapabilitySpec(owner="knowledge",
            id="knowledge.proposal.list",
            version=1,
            description="列出当前管理员可审核的知识提案。",
            permissions=("knowledge.manage",),
            plugin_callable=True,
            input_schema={"type": "object", "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}}},
            output_schema=PROPOSAL_LIST_SCHEMA,
            tags=("knowledge", "review", "read"),
        ),
        list_proposals,
    )
    register_capability(registry,
        CapabilitySpec(owner="knowledge",
            id="knowledge.proposal.get",
            version=1,
            description="获取一份知识提案的完整 Markdown 和审核状态。",
            permissions=("knowledge.manage",),
            plugin_callable=True,
            input_schema={"type": "object", "required": ["proposal_gid"], "properties": {"proposal_gid": {"type": "string"}}},
            output_schema=PROPOSAL_SCHEMA,
            tags=("knowledge", "review", "read"),
        ),
        get_proposal,
    )
