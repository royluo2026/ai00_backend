import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from backend.capability_governance_test.release_gate import ReleaseCandidate, ReleaseGate, ReleaseGateError


def _candidate() -> ReleaseCandidate:
    return ReleaseCandidate("rev-a", "catalog-a", 101, 201)


def _passing_inputs(**overrides):
    values = {
        "available": True,
        "test_status": "passed",
        "findings": (),
        "stale_evidence": False,
        "waivers": (),
        "approvals_complete": True,
        "data_complete": True,
        "idempotency_key": "gate-1",
    }
    values.update(overrides)
    return values


def test_release_gate_fails_when_required_runner_is_unavailable():
    report = ReleaseGate(next_gid=iter(range(1, 10)).__next__, signer=lambda value: "sig").evaluate(_candidate(), **_passing_inputs(test_status="unavailable"))

    assert report.conclusion == "fail"
    assert "required_test_unavailable" in report.blockers


def test_release_gate_fails_closed_for_missing_data_findings_stale_evidence_expired_waiver_and_incomplete_approval():
    report = ReleaseGate(next_gid=iter(range(1, 10)).__next__, signer=lambda value: "sig").evaluate(_candidate(), **_passing_inputs(data_complete=False, findings=({"code": "provider_missing", "severity": "blocking"},), stale_evidence=True, waivers=({"status": "expired"},), approvals_complete=False))

    assert report.conclusion == "fail"
    assert set(report.blockers) >= {"missing_required_data", "provider_missing", "stale_evidence", "expired_waiver", "incomplete_approvals"}


def test_passing_report_is_immutable_signed_and_expires_when_pinned_input_changes():
    gate = ReleaseGate(next_gid=iter(range(1, 10)).__next__, signer=lambda value: "signature:" + hashlib.sha256(value).hexdigest(), signing_key_id="release-test")
    report = gate.evaluate(_candidate(), **_passing_inputs())

    assert report.conclusion == "pass"
    assert report.signature.startswith("signature:")
    assert report.report_hash.startswith("sha256:")
    expired = gate.expire_changed_inputs(code_revision="rev-b")
    assert expired != (report.release_report_gid,)
    assert gate.get(report.release_report_gid) == report
    expired_report = gate.get(expired[0])
    assert expired_report.conclusion == "expired"
    assert expired_report.signature != report.signature
    assert expired_report.report_hash != report.report_hash


def test_release_gate_requires_idempotency_key_and_fails_active_waiver_after_expiry():
    gate = ReleaseGate(next_gid=iter(range(1, 20)).__next__, signer=lambda value: "sig")
    with pytest.raises(ReleaseGateError, match="idempotency_key_required"):
        gate.evaluate(_candidate(), **_passing_inputs(idempotency_key=""))

    report = gate.evaluate(_candidate(), **_passing_inputs(idempotency_key="gate-expired", waivers=({"status": "active", "starts_at": datetime(2026, 8, 1, tzinfo=timezone.utc), "expires_at": datetime(2026, 8, 2, tzinfo=timezone.utc), "code_hash": "rev-a", "catalog_hash": "catalog-a", "evidence_hash": "evidence-a"},), evidence_hash="evidence-a", now=datetime(2026, 8, 18, tzinfo=timezone.utc)))
    assert report.conclusion == "fail"
    assert "expired_waiver" in report.blockers


def test_release_gate_rejects_stale_waiver_hashes():
    report = ReleaseGate(next_gid=iter(range(1, 20)).__next__, signer=lambda value: "sig").evaluate(_candidate(), **_passing_inputs(idempotency_key="gate-stale", waivers=({"status": "active", "starts_at": datetime(2026, 8, 1, tzinfo=timezone.utc), "expires_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "code_hash": "rev-old", "catalog_hash": "catalog-a", "evidence_hash": "evidence-a"},), evidence_hash="evidence-a", now=datetime(2026, 8, 18, tzinfo=timezone.utc)))
    assert report.conclusion == "fail"
    assert "stale_waiver" in report.blockers
