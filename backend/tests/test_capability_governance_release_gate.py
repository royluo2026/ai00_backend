import hashlib
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.capability_governance_test.release_gate import ReleaseCandidate, ReleaseGate, ReleaseGateError
from backend.capability_v2.release_gate import BusinessGateCapability, evaluate_business_governance_gate
from backend.scripts.build_capability_v2_production_artifact import validate_release_report


VERSION_GID = "cv2_0123456789abcdef01234567"
DEFINITION_HASH = "sha256:" + "a" * 64


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
        "business_governance": evaluate_business_governance_gate((BusinessGateCapability(
            capability_key="person.height.write@1",
            capability_version_gid=VERSION_GID,
            definition_hash=DEFINITION_HASH,
            approved_definition_hash=DEFINITION_HASH,
            change_kind="new",
            human_approved=True,
            runtime_verified=True,
        ),)),
        "idempotency_key": "gate-1",
    }
    values.update(overrides)
    return values


def test_release_gate_fails_when_required_runner_is_unavailable():
    report = ReleaseGate(next_gid=iter(range(1, 10)).__next__, signer=lambda value: "sig").evaluate(_candidate(), **_passing_inputs(test_status="unavailable"))

    assert report.conclusion == "fail"
    assert "required_test_unavailable" in report.blockers


def test_signed_report_preserves_legacy_backlog_without_claiming_human_or_runtime_verification():
    governance = evaluate_business_governance_gate((BusinessGateCapability(
        capability_key="person.height.write@1",
        capability_version_gid=VERSION_GID,
        definition_hash=DEFINITION_HASH,
        change_kind="unchanged_legacy",
    ),))
    report = ReleaseGate(
        next_gid=iter(range(1, 10)).__next__, signer=lambda value: "sig",
    ).evaluate(_candidate(), **_passing_inputs(
        business_governance=governance,
        idempotency_key="legacy-backlog",
    ))

    assert report.conclusion == "pass"
    assert report.business_governance["status"] == "passed_with_legacy_backlog"
    assert report.business_governance["human_approved"] is False
    assert report.business_governance["runtime_verified"] is False
    assert report.to_document()["business_governance"] == report.business_governance


def test_static_green_cannot_override_unapproved_new_business_definition():
    governance = evaluate_business_governance_gate((BusinessGateCapability(
        capability_key="person.height.write@1",
        capability_version_gid=VERSION_GID,
        definition_hash=DEFINITION_HASH,
        change_kind="new",
    ),))
    report = ReleaseGate(
        next_gid=iter(range(1, 10)).__next__, signer=lambda value: "sig",
    ).evaluate(_candidate(), **_passing_inputs(
        business_governance=governance,
        idempotency_key="unapproved-new",
    ))

    assert report.conclusion == "fail"
    assert "business_governance_blocked" in report.blockers
    assert report.business_governance["machine_passed"] is True
    assert report.business_governance["human_approved"] is False


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
    assert gate.resolve(report.release_report_gid) == expired_report
    assert gate.resolve(report.release_report_gid).conclusion == "expired"


def test_passing_release_gate_report_verifies_in_production_artifact_checker(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    gate = ReleaseGate(
        next_gid=iter(range(501, 510)).__next__,
        signer=lambda payload: base64.b64encode(private_key.sign(payload)).decode("ascii"),
        signing_key_id="release-test",
    )

    report = gate.evaluate(_candidate(), **_passing_inputs())
    report_path = tmp_path / "release-report.json"
    report_path.write_text(json.dumps(report.to_document()), encoding="utf-8")

    assert validate_release_report(report_path, {"release-test": public_key}) == ()


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
