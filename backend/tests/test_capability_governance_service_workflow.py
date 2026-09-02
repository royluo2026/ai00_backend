from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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


def test_release_handler_does_not_accept_caller_supplied_green_evidence_without_authoritative_loader():
    service = CapabilityGovernanceService(
        release_gate=ReleaseGate(
            next_gid=iter(range(500, 600)).__next__, signer=lambda _payload: "signature", signing_key_id="test-key",
        ),
    )

    result = service.base_capability_release_gate_evaluate({
        "code_revision": "rev-forged", "product_catalog_release_id": "catalog-forged",
        "snapshot_gid": "101", "test_run_gid": "201", "available": True,
        "test_status": "passed", "findings": (), "stale_evidence": False,
        "waivers": (), "approvals_complete": True, "data_complete": True,
        "evidence_hash": "sha256:forged", "idempotency_key": "release-forged",
    }, _context(user_gid="attacker"))

    assert result["release"].conclusion == "fail"
    assert "governance_dependency_unavailable" in result["release"].blockers


def test_release_handler_uses_authoritative_pinned_evidence_instead_of_caller_statuses():
    class Store:
        def get_snapshot(self, snapshot_gid):
            if int(snapshot_gid) != 101:
                return None
            return SimpleNamespace(
                snapshot_gid=101,
                document=SimpleNamespace(
                    code_revision="rev-authoritative", product_release_id="catalog-authoritative",
                    snapshot_hash="sha256:snapshot",
                ),
            )

    class Authority:
        def resolve_test_run_gid(self, snapshot):
            assert snapshot.snapshot_gid == 101
            return 201

        def load_release_evidence(self, candidate, snapshot):
            assert candidate.snapshot_gid == 101
            assert snapshot.snapshot_gid == 101
            return {
                "snapshot_gid": 101, "test_run_gid": 201,
                "code_revision": "rev-authoritative", "product_catalog_release_id": "catalog-authoritative",
                "snapshot_hash": "sha256:snapshot", "test_status": "failed",
                "static_gate_status": "passed", "static_gate_hash": "sha256:static",
                "findings": (), "stale_evidence": False, "waivers": (),
                "approvals_complete": True, "data_complete": True,
                "evidence_hash": "sha256:authoritative",
            }

    service = CapabilityGovernanceService(
        Store(), release_evidence_port=Authority(),
        release_gate=ReleaseGate(
            next_gid=iter(range(600, 700)).__next__, signer=lambda _payload: "signature", signing_key_id="test-key",
        ),
    )
    result = service.base_capability_release_gate_evaluate({
        "target_gid": "101", "available": True,
        "test_status": "passed", "findings": (), "stale_evidence": False,
        "waivers": (), "approvals_complete": True, "data_complete": True,
        "evidence_hash": "sha256:forged", "idempotency_key": "release-authoritative",
    }, _context(user_gid="releaser"))

    assert result["release"].conclusion == "fail"
    assert "required_test_not_passed" in result["release"].blockers
