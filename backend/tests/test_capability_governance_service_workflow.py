from datetime import datetime, timedelta, timezone

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capability_governance_test.audit import AuditSink
from backend.capability_governance_test.release_gate import ReleaseGate
from backend.capability_governance_test.service import CapabilityGovernanceService


NOW = datetime(2026, 8, 19, tzinfo=timezone.utc)


def _context(*, user_gid: str = "author", roles: tuple[str, ...] = (), permissions: tuple[str, ...] = (), domains: tuple[str, ...] = ()) -> CapabilityContext:
    return CapabilityContext(
        user_gid=user_gid,
        active_roles=roles,
        permissions=permissions,
        owned_domains=domains,
    )


def _proposal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "capability_id": "base.capability_registry.search",
        "capability_version_gid": "17",
        "base_snapshot_gid": "31",
        "previous_hash": "sha256:old",
        "proposed_descriptor_hash": "sha256:new",
        "evidence_hash": "sha256:evidence",
        "idempotency_key": "proposal-1",
    }
    payload.update(overrides)
    return payload


def test_proposal_handler_uses_workflow_transitions_and_retains_idempotent_audit_evidence():
    audit = AuditSink(next_gid=iter(range(100, 200)).__next__)
    service = CapabilityGovernanceService(audit_sink=audit)

    submitted = service.base_capability_proposal_submit(_proposal_payload(), _context())
    repeated = service.base_capability_proposal_submit(_proposal_payload(), _context())

    assert submitted["proposal"].status == "submitted"
    assert repeated["proposal"] == submitted["proposal"]
    assert [event.operation for event in audit.events] == ["proposal", "proposal", "proposal"]

    with pytest.raises(CapabilityBusinessError, match="invalid_transition"):
        service.base_capability_review_decide({
            "proposal_gid": str(submitted["proposal"].proposal_gid),
            "stage": "base_owner",
            "decision": "approved",
            "row_version": str(submitted["proposal"].row_version),
            "idempotency_key": "review-1",
        }, _context(user_gid="reviewer", roles=("base_owner",), permissions=("system.capability.govern",), domains=("base",)))


def test_waiver_and_release_handlers_fail_closed_on_expiry_and_missing_approvals():
    audit = AuditSink(next_gid=iter(range(100, 200)).__next__)
    service = CapabilityGovernanceService(
        audit_sink=audit,
        release_gate=ReleaseGate(
            next_gid=iter(range(300, 400)).__next__, signer=lambda _payload: "signature", signing_key_id="test-key", audit_sink=audit,
        ),
    )

    with pytest.raises(CapabilityBusinessError, match="waiver_expiry_required"):
        service.base_capability_waiver_grant({
            "finding_gid": "5", "capability_version_gid": "17", "scope": "rule", "reason": "temporary",
            "code_hash": "rev-a", "catalog_hash": "catalog-a", "evidence_hash": "evidence-a",
            "idempotency_key": "waiver-no-expiry",
        }, _context())

    waiver = service.base_capability_waiver_grant({
        "finding_gid": "5", "capability_version_gid": "17", "scope": "rule", "reason": "temporary",
        "code_hash": "rev-a", "catalog_hash": "catalog-a", "evidence_hash": "evidence-a",
        "starts_at": (NOW - timedelta(days=2)).isoformat(), "expires_at": (NOW - timedelta(days=1)).isoformat(),
        "idempotency_key": "waiver-expired",
    }, _context())

    assert waiver["waiver"].status == "expired"

    release = service.base_capability_release_gate_evaluate({
        "code_revision": "rev-a", "product_catalog_release_id": "catalog-a", "snapshot_gid": "31", "test_run_gid": "41",
        "test_status": "passed", "approvals_complete": False, "data_complete": True,
        "evidence_hash": "evidence-a", "waivers": (waiver["waiver"],), "idempotency_key": "release-1",
    }, _context(user_gid="releaser"))

    assert release["release"].conclusion == "fail"
    assert set(release["release"].blockers) >= {"expired_waiver", "incomplete_approvals"}
    assert {event.operation for event in audit.events} >= {"waiver", "gate"}

    missing_evidence = service.base_capability_release_gate_evaluate({
        "code_revision": "rev-b", "product_catalog_release_id": "catalog-b", "snapshot_gid": "32", "test_run_gid": "42",
        "available": True, "test_status": "passed", "approvals_complete": True, "data_complete": True,
        "idempotency_key": "release-missing-evidence",
    }, _context(user_gid="releaser"))

    assert missing_evidence["release"].conclusion == "fail"
    assert "missing_required_data" in missing_evidence["release"].blockers
