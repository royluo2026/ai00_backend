"""Review and publish knowledge proposals."""
from __future__ import annotations

import json
import hashlib
from typing import Any

def review_proposal(payload: dict[str, Any], context) -> dict[str, Any]:
    proposal_gid = str(payload.get("proposal_gid") or "").strip()
    decision = str(payload.get("decision") or "").strip().lower()
    note = str(payload.get("review_note") or "").strip()[:4000]
    if not proposal_gid:
        raise ValueError("proposal_gid is required")
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")

    from backend.db.connection import get_conn
    from backend.utils.gid import next_gid
    from backend.capabilities.outbox_next import enqueue_publish, mark_complete

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_know_proposals WHERE gid = %s FOR UPDATE",
                (proposal_gid,),
            )
            proposal = cur.fetchone()
            if not proposal:
                raise LookupError("知识提案不存在")
            proposal = dict(proposal)
            if proposal.get("status") != "pending":
                raise ValueError(f"提案当前状态为 {proposal.get('status')}，不能重复审核")

            if decision == "rejected":
                cur.execute(
                    "UPDATE workmanship_know_proposals SET status='rejected', reviewer_gid=%s, review_note=%s, reviewed_at=NOW(), updated_at=NOW() WHERE gid=%s",
                    (context.user_gid, note, proposal_gid),
                )
                conn.commit()
                return {"proposal_gid": proposal_gid, "status": "rejected", "reviewer_gid": context.user_gid}

            outbox_gid = str(next_gid())
            enqueue_publish(
                proposal_gid,
                {"proposal_gid": proposal_gid},
                gid=outbox_gid,
                error="publication_started",
            )

            # OIS is authoritative for published Markdown. Do not publish a
            # formal entry when OIS is unavailable.
            from backend.core.ois_storage import upload

            content_md = str(proposal.get("content_md") or "")
            ois_url = upload(content_md.encode("utf-8"), ".md", "text/markdown", prefix="knowledge")
            if not ois_url:
                raise RuntimeError("OIS 不可用，提案保持 pending，未发布正式知识")

            published_gid = str(next_gid())
            content_sha256 = hashlib.sha256(content_md.encode("utf-8")).hexdigest()
            content_ref = json.dumps({"ois_url": ois_url, "proposal_gid": proposal_gid, "sha256": content_sha256}, ensure_ascii=False)
            tags = proposal.get("tags") or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except (TypeError, ValueError):
                    tags = []
            cur.execute(
                """INSERT INTO workmanship_know_entries
                   (gid, display_id, title, entry_type, content_ref, content_md,
                    tags, status, share_scope, creator_gid, source_gid, source_label,
                    created_at, updated_at)
                   VALUES (%s, '', %s, 'guide', %s, %s, %s, 'published',
                           'team', %s, %s, 'knowledge.proposal', NOW(), NOW())""",
                (
                    published_gid,
                    proposal.get("title") or "",
                    content_ref,
                    content_md,
                    json.dumps(tags, ensure_ascii=False),
                    proposal.get("creator_gid") or context.user_gid,
                    proposal_gid,
                ),
            )
            cur.execute(
                "UPDATE workmanship_know_proposals SET status='approved', reviewer_gid=%s, review_note=%s, reviewed_at=NOW(), published_gid=%s, ois_url=%s, updated_at=NOW() WHERE gid=%s",
                (context.user_gid, note, published_gid, ois_url, proposal_gid),
            )
        conn.commit()
    mark_complete(outbox_gid)
    return {
        "proposal_gid": proposal_gid,
        "status": "approved",
        "published_gid": published_gid,
        "ois_url": ois_url,
        "reviewer_gid": context.user_gid,
    }


def register_review_capability(registry) -> None:
    from .models_next import CapabilitySpec

    registry.register(
        CapabilitySpec(
            id="knowledge.proposal.review",
            version=1,
            description="审核知识提案；通过后将 Markdown 写入 OIS 并生成正式知识条目。",
            risk="write",
            confirmation="user",
            permissions=("knowledge.manage",),
            input_schema={
                "type": "object",
                "required": ["proposal_gid", "decision"],
                "properties": {
                    "proposal_gid": {"type": "string"},
                    "decision": {"type": "string"},
                    "review_note": {"type": "string"},
                },
            },
            output_schema={"type": "object"},
            idempotent=False,
            tags=("knowledge", "write", "review"),
        ),
        review_proposal,
    )
