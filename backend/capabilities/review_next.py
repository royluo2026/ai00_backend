"""Review and publish knowledge proposals."""
from __future__ import annotations

import json
from typing import Any
from backend.knowledge.contracts import PROPOSAL_SCHEMA, proposal_ref
from backend.knowledge.provider import register_capability
from backend.knowledge.ids import new_knowledge_id
from backend.capabilities.models_next import CapabilityBusinessError

def review_proposal(payload: dict[str, Any], context) -> dict[str, Any]:
    proposal_gid = str(payload.get("proposal_gid") or "").strip()
    decision = str(payload.get("decision") or "").strip().lower()
    note = str(payload.get("review_note") or "").strip()[:4000]
    if not proposal_gid:
        raise ValueError("proposal_gid is required")
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")

    from backend.knowledge.data.connection import get_knowledge_conn as get_conn
    from backend.capabilities.outbox_retry_next import retry_publish

    team_gid = str(context.team_gid or "").strip()
    if not team_gid:
        raise CapabilityBusinessError(
            "tenant_scope_denied", "Knowledge proposal review requires a team tenant."
        )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_know_proposals WHERE gid=%s AND team_gid=%s FOR UPDATE",
                (proposal_gid, team_gid),
            )
            proposal = cur.fetchone()
            if not proposal:
                raise LookupError("知识提案不存在")
            proposal = dict(proposal)
            if proposal.get("status") != "pending":
                raise CapabilityBusinessError(
                    "proposal_state_conflict",
                    "The proposal is no longer pending review.",
                    details={"proposal_gid": proposal_gid, "status": proposal.get("status")},
                )
            if str(proposal.get("creator_gid") or "") == str(context.user_gid):
                raise CapabilityBusinessError(
                    "self_review_forbidden", "Proposal creators cannot review their own proposal."
                )

            if decision == "rejected":
                cur.execute(
                    "UPDATE workmanship_know_proposals SET status='rejected', reviewer_gid=%s, review_note=%s, reviewed_at=NOW(), updated_at=NOW() WHERE gid=%s",
                    (context.user_gid, note, proposal_gid),
                )
                conn.commit()
                return {"object_ref": proposal_ref(proposal_gid), "proposal_gid": proposal_gid, "status": "rejected", "reviewer_gid": context.user_gid}

            if proposal.get("reviewer_gid"):
                if str(proposal["reviewer_gid"]) != str(context.user_gid):
                    raise CapabilityBusinessError(
                        "proposal_state_conflict",
                        "Another reviewer already accepted this proposal publication.",
                    )
                cur.execute(
                    "SELECT gid FROM workmanship_know_publish_outbox WHERE proposal_gid=%s "
                    "ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                    (proposal_gid,),
                )
                existing_outbox = cur.fetchone()
                if not existing_outbox:
                    raise CapabilityBusinessError(
                        "proposal_state_conflict",
                        "Reviewed proposal is missing its publication operation.",
                    )
                outbox_gid = str(existing_outbox["gid"])
            else:
                outbox_gid = new_knowledge_id("outbox")
                cur.execute(
                    "INSERT INTO workmanship_know_publish_outbox "
                    "(gid,proposal_gid,payload,status,attempts,last_error,created_at,updated_at) "
                    "VALUES (%s,%s,%s,'pending',0,NULL,NOW(),NOW())",
                    (outbox_gid, proposal_gid, json.dumps({"proposal_gid": proposal_gid})),
                )
                cur.execute(
                    "UPDATE workmanship_know_proposals SET status='publishing',reviewer_gid=%s,review_note=%s,"
                    "reviewed_at=NOW(),updated_at=NOW() WHERE gid=%s AND status='pending'",
                    (context.user_gid, note, proposal_gid),
                )
        conn.commit()

    publication = retry_publish({"outbox_gid": outbox_gid}, context)
    return {
        "object_ref": proposal_ref(proposal_gid),
        "proposal_gid": proposal_gid,
        "status": "approved",
        "published_gid": publication.get("published_gid"),
        "published_ref": publication.get("published_ref"),
        "reviewer_gid": context.user_gid,
    }


def register_review_capability(registry) -> None:
    from .models_next import CapabilitySpec

    register_capability(registry,
        CapabilitySpec(owner="knowledge",
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
                    "decision": {"type": "string", "enum": ["approved", "rejected"]},
                    "review_note": {"type": "string", "maxLength": 4000},
                },
            },
            output_schema=PROPOSAL_SCHEMA,
            idempotent=False,
            tags=("knowledge", "write", "review"),
        ),
        review_proposal,
    )
