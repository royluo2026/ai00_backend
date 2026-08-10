"""Knowledge proposal capability: write a reviewable Markdown draft."""
from __future__ import annotations

import json
from typing import Any

from .models_next import CapabilityContext
from backend.knowledge.contracts import PROPOSAL_SCHEMA, proposal_ref
from backend.knowledge.provider import register_capability
from backend.knowledge.ids import new_knowledge_id



def propose_knowledge(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    content_md = str(payload.get("content_md") or "")
    if not title:
        raise ValueError("title is required")
    if len(title) > 255:
        raise ValueError("title is too long")
    if not content_md.strip():
        raise ValueError("content_md is required")
    if len(content_md) > 200_000:
        raise ValueError("content_md exceeds 200000 characters")
    tags = payload.get("tags") or []
    if not isinstance(tags, list) or len(tags) > 50:
        raise ValueError("tags must be an array with at most 50 items")

    from backend.knowledge.data.connection import get_knowledge_conn as get_conn
    gid = new_knowledge_id("proposal")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_know_proposals
                   (gid, base_gid, title, content_md, summary, tags, status,
                    creator_gid, team_gid, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, NOW(), NOW())""",
                (
                    gid,
                    str(payload.get("base_gid") or "").strip() or None,
                    title,
                    content_md,
                    str(payload.get("summary") or "").strip()[:2000],
                    json.dumps(tags, ensure_ascii=False),
                    context.user_gid,
                    context.team_gid,
                ),
            )
        conn.commit()
    return {
        "object_ref": proposal_ref(gid),
        "proposal_gid": gid,
        "status": "pending",
        "title": title,
        "creator_gid": context.user_gid,
        "message": "知识提案已提交，等待评审",
    }


def register_proposal_capability(registry) -> None:
    from .models_next import CapabilitySpec

    register_capability(registry,
        CapabilitySpec(owner="knowledge",
            id="knowledge.propose",
            version=1,
            description="提交一份待评审的 Markdown 知识提案，不直接修改正式知识库。",
            risk="write",
            confirmation="user",
            permissions=("knowledge.view",),
            input_schema={
                "type": "object",
                "required": ["title", "content_md"],
                "properties": {
                    "title": {"type": "string"},
                    "content_md": {"type": "string"},
                    "summary": {"type": "string"},
                    "base_gid": {"type": "string"},
                    "tags": {"type": "array", "maxItems": 50, "items": {"type": "string"}},
                },
            },
            output_schema=PROPOSAL_SCHEMA,
            idempotent=False,
            tags=("knowledge", "write", "proposal"),
        ),
        propose_knowledge,
    )
