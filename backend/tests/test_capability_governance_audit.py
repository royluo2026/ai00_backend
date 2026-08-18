import pytest
from datetime import datetime, timezone

from backend.capability_governance_test.audit import AuditError, AuditSink
from backend.capability_governance_test.release_gate import ReleaseCandidate, ReleaseGate
from backend.capability_governance_test.workflow import ProposalService, ReviewerContext, WaiverService


@pytest.mark.parametrize("operation", ("scan", "analysis", "confirmation", "rejection", "proposal", "review", "waiver", "test", "gate", "prompt_generation", "agent_invocation"))
def test_audit_sink_appends_one_redacted_event_for_each_governance_operation(operation):
    sink = AuditSink(next_gid=iter(range(1, 100)).__next__)

    event = sink.append(operation=operation, entity_gid=9, actor_gid="agent-1", request_gid="request-1", detail={"password": "p@ss", "api_token": "token-value", "endpoint_url": "https://user:secret@example.test/path", "safe": "value"}, idempotency_key=operation)

    assert sink.events == (event,)
    assert event.detail["safe"] == "value"
    rendered = repr(event.detail).lower()
    assert "p@ss" not in rendered
    assert "token-value" not in rendered
    assert "user:secret" not in rendered


def test_audit_events_are_append_only_and_idempotent():
    sink = AuditSink(next_gid=iter(range(1, 100)).__next__)
    first = sink.append(operation="scan", entity_gid=9, actor_gid="agent-1", request_gid="request-1", detail={}, idempotency_key="scan-1")

    assert sink.append(operation="scan", entity_gid=9, actor_gid="agent-1", request_gid="request-1", detail={}, idempotency_key="scan-1") == first
    with pytest.raises(AuditError, match="append_only"):
        sink.update(first.audit_event_gid, detail={})


def test_services_emit_audit_events_for_proposal_review_waiver_and_gate():
    sink = AuditSink(next_gid=iter(range(1, 100)).__next__)
    proposals = ProposalService(next_gid=iter(range(100, 200)).__next__, audit_sink=sink)
    proposal = proposals.detect(capability_id="craft.order.submit", capability_version_gid=17, base_snapshot_gid=31, previous_hash="sha256:old", proposed_descriptor_hash="sha256:new", evidence_hash="sha256:e", submitted_by_gid="author", idempotency_key="detect")
    draft = proposals.transition(proposal.proposal_gid, "draft", expected_row_version=proposal.row_version, idempotency_key="draft")
    submitted = proposals.submit(draft.proposal_gid, expected_row_version=draft.row_version, idempotency_key="submit")
    checking = proposals.transition(submitted.proposal_gid, "checking", expected_row_version=submitted.row_version, idempotency_key="checking")
    pending = proposals.transition(checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version, idempotency_key="pending")
    proposals.decide(pending.proposal_gid, stage="base_owner", decision="approved", reviewer_context=ReviewerContext("base-owner", ("base_owner",), ("system.capability.govern",), ("base",)), expected_row_version=pending.row_version, idempotency_key="review")
    WaiverService(next_gid=iter(range(200, 300)).__next__, audit_sink=sink).grant(finding_gid=1, capability_version_gid=2, scope="rule", reason="reason", granted_by_gid="owner", code_hash="rev-a", catalog_hash="catalog-a", evidence_hash="evidence-a", expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc), idempotency_key="waiver")
    ReleaseGate(next_gid=iter(range(300, 400)).__next__, signer=lambda value: "sig", audit_sink=sink).evaluate(ReleaseCandidate("rev-a", "catalog-a", 101, 201), available=True, test_status="passed", approvals_complete=True, data_complete=True, idempotency_key="gate")

    assert {event.operation for event in sink.events} >= {"proposal", "review", "waiver", "gate"}


def test_supersession_and_expiry_append_auditable_state_events():
    sink = AuditSink(next_gid=iter(range(1, 100)).__next__)
    proposals = ProposalService(next_gid=iter(range(100, 200)).__next__, audit_sink=sink)
    first = proposals.detect(capability_id="craft.order.submit", capability_version_gid=17, base_snapshot_gid=31, previous_hash="sha256:old", proposed_descriptor_hash="sha256:a", evidence_hash="sha256:e", submitted_by_gid="author", idempotency_key="detect-a")
    proposals.detect(capability_id="craft.order.submit", capability_version_gid=17, base_snapshot_gid=32, previous_hash="sha256:a", proposed_descriptor_hash="sha256:b", evidence_hash="sha256:e", submitted_by_gid="author", idempotency_key="detect-b")
    supersession = next(event for event in sink.events if event.operation == "proposal_superseded")
    assert supersession.entity_gid == first.proposal_gid
    assert supersession.detail["after_status"] == "superseded"

    gate = ReleaseGate(next_gid=iter(range(300, 400)).__next__, signer=lambda value: "sig", audit_sink=sink)
    report = gate.evaluate(ReleaseCandidate("rev-a", "catalog-a", 101, 201), available=True, test_status="passed", approvals_complete=True, data_complete=True, idempotency_key="gate-a")
    expiry_gid = gate.expire_changed_inputs(code_revision="rev-b")[0]
    expiry = next(event for event in sink.events if event.operation == "release_report_expired")
    assert expiry.entity_gid == expiry_gid
    assert expiry.detail["supersedes_release_report_gid"] == report.release_report_gid
