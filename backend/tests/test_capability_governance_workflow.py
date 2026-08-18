from datetime import datetime, timedelta, timezone

import pytest

from backend.capability_governance_test.workflow import (
    ProposalService,
    ReviewerContext,
    WaiverService,
    WorkflowError,
    transition_state,
)


NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


def _reviewer(gid: str, *, role: str = "base_owner", permission: str = "system.capability.govern", domain: str = "base") -> ReviewerContext:
    return ReviewerContext(gid=gid, roles=(role,), permissions=(permission,), owned_domains=(domain,))


def test_capability_and_finding_state_machines_reject_unlisted_edges():
    assert transition_state("capability", "experimental", "stable") == "stable"
    assert transition_state("capability", "stable", "deprecated") == "deprecated"
    assert transition_state("capability", "deprecated", "retired") == "retired"
    assert transition_state("finding", "candidate", "confirmed") == "confirmed"
    with pytest.raises(WorkflowError, match="invalid_transition"):
        transition_state("capability", "stable", "experimental")
    for current, target in (("experimental", "deprecated"), ("experimental", "retired"), ("stable", "retired")):
        with pytest.raises(WorkflowError, match="invalid_transition"):
            transition_state("capability", current, target)
    with pytest.raises(WorkflowError, match="invalid_transition"):
        transition_state("finding", "confirmed", "candidate")


def _submitted(service: ProposalService, *, capability_id: str = "craft.order.submit", submitted_by: str = "author-1"):
    proposal = service.detect(
        capability_id=capability_id,
        capability_version_gid=17,
        base_snapshot_gid=31,
        previous_hash="sha256:old",
        proposed_descriptor_hash="sha256:a",
        evidence_hash="sha256:evidence-a",
        submitted_by_gid=submitted_by,
        idempotency_key="detect-1",
    )
    proposal = service.transition(proposal.proposal_gid, "draft", expected_row_version=proposal.row_version, idempotency_key="draft-1")
    return service.submit(proposal.proposal_gid, expected_row_version=proposal.row_version, idempotency_key="submit-1")


def test_code_hash_change_stales_approved_proposal():
    service = ProposalService(next_gid=iter(range(100, 200)).__next__)
    proposal = _submitted(service)
    checking = service.transition(proposal.proposal_gid, "checking", expected_row_version=proposal.row_version, idempotency_key="checking-1")
    pending = service.transition(checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version, idempotency_key="pending-1")
    approved = service.decide(pending.proposal_gid, stage="base_owner", decision="approved", reviewer_context=_reviewer("reviewer-1"), expected_row_version=pending.row_version, idempotency_key="review-1", decided_at=NOW)

    stale = service.refresh(approved.proposal_gid, current_descriptor_hash="sha256:b", current_evidence_hash="sha256:evidence-a", expected_row_version=approved.row_version, idempotency_key="refresh-1")

    assert stale.status == "stale"


def test_governance_capability_cannot_self_approve_and_requires_two_independent_stages():
    service = ProposalService(next_gid=iter(range(100, 200)).__next__)
    proposal = _submitted(service, capability_id="base.capability_review.decide", submitted_by="agent-1")
    checking = service.transition(proposal.proposal_gid, "checking", expected_row_version=proposal.row_version, idempotency_key="checking-1")
    pending = service.transition(checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version, idempotency_key="pending-1")

    with pytest.raises(WorkflowError, match="independent_reviewer_required"):
        service.decide(pending.proposal_gid, stage="base_owner", decision="approved", reviewer_context=_reviewer("agent-1"), expected_row_version=pending.row_version, idempotency_key="self-review", decided_at=NOW)

    base_approved = service.decide(pending.proposal_gid, stage="base_owner", decision="approved", reviewer_context=_reviewer("base-owner"), expected_row_version=pending.row_version, idempotency_key="base-review", decided_at=NOW)
    assert base_approved.status == "pending_approval"
    with pytest.raises(WorkflowError, match="independent_reviewer_required"):
        service.decide(base_approved.proposal_gid, stage="platform_release", decision="approved", reviewer_context=_reviewer("base-owner", role="platform_release", permission="system.capability.release", domain="platform"), expected_row_version=base_approved.row_version, idempotency_key="same-reviewer", decided_at=NOW)
    approved = service.decide(base_approved.proposal_gid, stage="platform_release", decision="approved", reviewer_context=_reviewer("platform-release", role="platform_release", permission="system.capability.release", domain="platform"), expected_row_version=base_approved.row_version, idempotency_key="platform-review", decided_at=NOW)
    assert approved.status == "approved"


def test_ai_advisory_identity_cannot_approve_and_unlisted_transitions_are_rejected():
    service = ProposalService(next_gid=iter(range(100, 200)).__next__)
    proposal = _submitted(service)

    with pytest.raises(WorkflowError, match="invalid_transition"):
        service.transition(proposal.proposal_gid, "released", expected_row_version=proposal.row_version, idempotency_key="invalid")
    checking = service.transition(proposal.proposal_gid, "checking", expected_row_version=proposal.row_version, idempotency_key="checking-1")
    pending = service.transition(checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version, idempotency_key="pending-1")
    with pytest.raises(WorkflowError, match="independent_reviewer_required"):
        service.decide(pending.proposal_gid, stage="base_owner", decision="approved", reviewer_context=_reviewer("ai:advisor"), expected_row_version=pending.row_version, idempotency_key="ai-review", decided_at=NOW)


@pytest.mark.parametrize("context", (
    _reviewer("not-owner", domain="craft"),
    _reviewer("wrong-role", role="platform_release", permission="system.capability.release", domain="platform"),
    _reviewer("missing-permission", permission="system.capability.read"),
))
def test_review_stage_requires_authorized_base_owner(context: ReviewerContext):
    service = ProposalService(next_gid=iter(range(100, 200)).__next__)
    proposal = _submitted(service)
    checking = service.transition(proposal.proposal_gid, "checking", expected_row_version=proposal.row_version, idempotency_key="checking-1")
    pending = service.transition(checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version, idempotency_key="pending-1")

    with pytest.raises(WorkflowError, match="reviewer_not_authorized"):
        service.decide(pending.proposal_gid, stage="base_owner", decision="approved", reviewer_context=context, expected_row_version=pending.row_version, idempotency_key="wrong-authority", decided_at=NOW)


def test_detect_is_idempotent_and_updates_require_current_row_version():
    service = ProposalService(next_gid=iter(range(100, 200)).__next__)
    first = service.detect(capability_id="craft.order.submit", capability_version_gid=17, base_snapshot_gid=31, previous_hash="sha256:old", proposed_descriptor_hash="sha256:new", evidence_hash="sha256:e", submitted_by_gid="author", idempotency_key="same")
    repeated = service.detect(capability_id="craft.order.submit", capability_version_gid=17, base_snapshot_gid=31, previous_hash="sha256:old", proposed_descriptor_hash="sha256:new", evidence_hash="sha256:e", submitted_by_gid="author", idempotency_key="same")

    assert repeated == first
    with pytest.raises(WorkflowError, match="row_version_conflict"):
        service.transition(first.proposal_gid, "draft", expected_row_version=99, idempotency_key="version-conflict")


def test_waiver_must_expire_and_expired_waiver_is_not_effective():
    service = WaiverService(next_gid=iter(range(200, 300)).__next__)
    with pytest.raises(WorkflowError, match="waiver_expiry_required"):
        service.grant(finding_gid=1, capability_version_gid=2, scope="rule", reason="reason", granted_by_gid="owner", code_hash="rev-a", catalog_hash="catalog-a", evidence_hash="evidence-a", expires_at=None, idempotency_key="no-expiry")

    waiver = service.grant(finding_gid=1, capability_version_gid=2, scope="rule", reason="reason", granted_by_gid="owner", code_hash="rev-a", catalog_hash="catalog-a", evidence_hash="evidence-a", starts_at=NOW - timedelta(days=2), expires_at=NOW - timedelta(days=1), idempotency_key="expired")
    assert waiver.status == "expired"
    assert service.effective(waiver.waiver_gid, now=NOW) is False


def test_waiver_hash_change_makes_it_stale_and_revoke_requires_idempotency():
    service = WaiverService(next_gid=iter(range(200, 300)).__next__)
    waiver = service.grant(finding_gid=1, capability_version_gid=2, scope="rule", reason="reason", granted_by_gid="owner", code_hash="rev-a", catalog_hash="catalog-a", evidence_hash="evidence-a", starts_at=NOW, expires_at=NOW + timedelta(days=1), idempotency_key="active")

    with pytest.raises(WorkflowError, match="idempotency_key_required"):
        service.revoke(waiver.waiver_gid, expected_row_version=waiver.row_version, idempotency_key="")
    stale = service.refresh(waiver.waiver_gid, code_hash="rev-b", catalog_hash="catalog-a", evidence_hash="evidence-a", expected_row_version=waiver.row_version, idempotency_key="stale")
    assert stale.status == "stale"
