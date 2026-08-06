"""Governed ontology proposal and human review Capabilities."""
from __future__ import annotations

from typing import Any

from backend.ontology.proposals import (
    OntologyProposalRepository,
    ProposalConflict,
    ProposalIntegrityError,
    normalize_changes,
)
from backend.utils.gid import next_gid

from .models_next import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef


def _proposal_evidence(data: dict[str, Any]) -> EvidenceRef:
    digest = str(data["content_sha256"])
    return EvidenceRef(
        kind="ontology.proposal_revision",
        reference=f"ontology://proposals/{data['proposal_gid']}/revisions/{data['proposal_revision_gid']}",
        digest=f"sha256:{digest}",
        summary=f"Ontology proposal {data['proposal_gid']} immutable revision",
        metadata={"proposal_gid": data["proposal_gid"], "proposal_revision_gid": data["proposal_revision_gid"]},
    )


def create_proposal(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    base_release_gid = str(payload.get("base_release_gid") or "").strip()
    changes = normalize_changes(payload.get("changes") or [])
    repository = OntologyProposalRepository()
    active = repository.get_active()
    current = str(active.get("release_gid")) if active else None
    if not base_release_gid or current != base_release_gid:
        raise CapabilityBusinessError(
            "base_release_conflict", "The proposal base release is not the active ontology release.",
            details={"requested_base_release_gid": base_release_gid, "active_release_gid": current},
        )
    try:
        data = repository.create(
            proposal_gid=str(next_gid()), revision_gid=str(next_gid()), base_release_gid=base_release_gid,
            changes=changes, author_gid=context.user_gid, channel=context.source,
        )
    except ProposalConflict as exc:
        raise CapabilityBusinessError("base_release_conflict", str(exc)) from exc
    return CapabilityOutput(data=data, evidence=(_proposal_evidence(data),))


def get_proposal(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    proposal_gid = str(payload.get("proposal_gid") or "").strip()
    data = OntologyProposalRepository().get(proposal_gid)
    if not data:
        raise LookupError("ontology proposal not found")
    return CapabilityOutput(data=data, evidence=(_proposal_evidence(data),))


def search_proposals(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    status = str(payload.get("status") or "").strip() or None
    limit = int(payload.get("limit") or 50)
    items = OntologyProposalRepository().search(status=status, limit=limit)
    return {"items": items, "total": len(items)}


def submit_review(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    if context.source not in {"web", "feishu"} or getattr(context, "agent_run_gid", None) or getattr(context, "agent_run_id", None):
        raise CapabilityBusinessError("human_review_required", "A human reviewer must submit ontology decisions.")
    decision = str(payload.get("decision") or "").strip()
    comment = str(payload.get("comment") or "").strip()[:4000] or None
    if decision == "request_changes" and not comment:
        raise ValueError("request_changes requires a comment")
    try:
        data = OntologyProposalRepository().save_review(
            review_gid=str(next_gid()), proposal_gid=str(payload.get("proposal_gid") or ""),
            proposal_revision_gid=str(payload.get("proposal_revision_gid") or ""),
            content_sha256=str(payload.get("content_sha256") or ""), decision=decision,
            reviewer_gid=context.user_gid, comment=comment,
        )
    except ProposalIntegrityError as exc:
        raise CapabilityBusinessError("proposal_revision_conflict", str(exc)) from exc
    except ProposalConflict as exc:
        raise CapabilityBusinessError("proposal_review_conflict", str(exc)) from exc
    return CapabilityOutput(data=data, evidence=(_proposal_evidence(data),))


def register_ontology_proposal_capabilities(registry: Any) -> None:
    common = {
        "owner": "ontology", "plugin_callable": True,
        "subject_concepts": ("ontology.proposal", "ontology.proposal_revision"),
        "output_schema": {"type": "object"}, "tags": ("ontology", "proposal"),
    }
    registry.register(CapabilitySpec(
        **common, id="ontology.change.proposal.create", description="Create an immutable typed proposal against the exact active release.",
        use_when="A governed ontology change is being proposed.", do_not_use_when="Direct mutation of an active release is expected.",
        effects=("create:ontology.proposal", "create:ontology.proposal_revision"), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["base_release_gid", "changes"]}), create_proposal)
    registry.register(CapabilitySpec(
        **common, id="ontology.change.proposal.get", description="Read the current immutable proposal revision.",
        use_when="A proposal GID is known.", do_not_use_when="Searching proposals.", effects=("read:ontology.proposal",),
        input_schema={"type": "object", "required": ["proposal_gid"]}), get_proposal)
    registry.register(CapabilitySpec(
        **common, id="ontology.change.proposal.search", description="Search proposal metadata by governed status.",
        use_when="A review queue or proposal list is required.", do_not_use_when="A proposal GID is known.", effects=("read:ontology.proposal",),
        input_schema={"type": "object"}), search_proposals)
    registry.register(CapabilitySpec(
        **common, id="ontology.change.proposal.review.submit", description="Append a human review bound to an immutable proposal revision Hash.",
        use_when="A human reviewer makes a formal decision.", do_not_use_when="An Agent is attempting to approve.",
        effects=("create:ontology.proposal_review",), risk="write", confirmation="user", idempotent=False,
        permissions=("ontology.review",), input_schema={"type": "object", "required": ["proposal_gid", "proposal_revision_gid", "content_sha256", "decision"]}), submit_review)
