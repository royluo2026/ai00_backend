from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.capability_governance_test.release_gate import ReleaseCandidate, ReleaseGate
from backend.capability_v2.release_gate import (
    BusinessGateCapability,
    BusinessGovernanceConfigurationError,
    create_legacy_baseline,
    evaluate_catalog_business_governance,
    evaluate_business_governance_gate,
    load_business_approval_artifact,
    load_legacy_baseline,
    parse_business_governance_result,
)
from backend.scripts.build_capability_v2_production_artifact import (
    _canonical_release_report,
    validate_release_report,
)
from backend.scripts import check_capability_v2_release_gate as release_gate_command


HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
VERSION_GID = "cv2_" + "a" * 24


def _governance(*, kind: str = "new", approved: bool = True):
    return evaluate_business_governance_gate((BusinessGateCapability(
        capability_key="person.height.write@1",
        capability_version_gid=VERSION_GID,
        definition_hash=HASH_1,
        approved_definition_hash=HASH_1 if approved else None,
        change_kind=kind,
        human_approved=approved,
    ),))


@pytest.mark.parametrize(
    "tamper",
    (
        lambda document: document["capabilities"][0].update(human_approved=False),
        lambda document: document["capabilities"][0].update(approved_definition_hash=HASH_2),
        lambda document: document["capabilities"][0].update(governance_status="blocked"),
        lambda document: document.update(legacy_pending_review_count=7),
        lambda document: document.update(blockers=["fabricated"]),
    ),
)
def test_canonical_governance_parser_rejects_nested_or_aggregate_bypass(tamper):
    document = _governance(approved=True).serialized()
    tamper(document)

    with pytest.raises(BusinessGovernanceConfigurationError, match="business_governance_invalid"):
        parse_business_governance_result(document)


def test_canonical_governance_parser_rederives_the_exact_valid_result():
    expected = _governance(kind="unchanged_legacy", approved=False)

    assert parse_business_governance_result(expected) == expected
    assert parse_business_governance_result(expected.serialized()) == expected


def test_production_artifact_rejects_a_resigned_nested_governance_bypass(tmp_path: Path):
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
    report = gate.evaluate(
        ReleaseCandidate("rev-a", "catalog-a", 101, 201),
        test_status="passed", approvals_complete=True, data_complete=True,
        evidence_hash=HASH_1, static_gate_status="passed", static_gate_hash=HASH_2,
        business_governance=_governance(), idempotency_key="signed-valid",
    ).to_document()
    report["business_governance"]["capabilities"][0]["human_approved"] = False
    canonical = _canonical_release_report(report)
    report["report_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    report["signature"] = base64.b64encode(private_key.sign(canonical)).decode("ascii")
    path = tmp_path / "tampered-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    assert "release_report_governance_invalid" in validate_release_report(
        path, {"release-test": public_key},
    )


def _catalog(path: Path) -> dict:
    source = Path(__file__).resolve().parents[2] / "docs/governance/capability-catalog-release.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def test_baseline_verification_is_bound_to_the_referenced_catalog(tmp_path: Path):
    catalog = tmp_path / "catalog.json"
    other = tmp_path / "other.json"
    baseline = tmp_path / "baseline.json"
    document = _catalog(catalog)
    tampered = _catalog(other)
    tampered["catalog_hash"] = HASH_2
    other.write_text(json.dumps(tampered), encoding="utf-8")
    create_legacy_baseline(catalog, baseline, source_revision="cutover")

    assert load_legacy_baseline(baseline, catalog_path=catalog).catalog_release_id == document["release_id"]
    with pytest.raises(BusinessGovernanceConfigurationError, match="legacy_baseline_catalog_(invalid|mismatch)"):
        load_legacy_baseline(baseline, catalog_path=other)


def test_approval_artifact_is_exactly_bound_to_version_and_definition_hash(tmp_path: Path):
    path = tmp_path / "approvals.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "catalog_release_id": "rel_exact",
        "approvals": [{
            "capability_key": "person.height.write@1",
            "capability_version_gid": VERSION_GID,
            "definition_hash": HASH_1,
            "decision": "approved",
        }],
    }), encoding="utf-8")

    approvals = load_business_approval_artifact(path, catalog_release_id="rel_exact")

    assert approvals.get((VERSION_GID, HASH_1)) == HASH_1
    assert approvals.get((VERSION_GID, HASH_2)) is None
    with pytest.raises(BusinessGovernanceConfigurationError, match="business_approval_catalog_mismatch"):
        load_business_approval_artifact(path, catalog_release_id="rel_other")


def test_catalog_gate_passes_only_with_the_exact_current_version_and_hash_approval():
    catalog = {"descriptors": [{
        "id": "person.height.write",
        "major_version": 1,
        "capability_version_gid": VERSION_GID,
        "business_definition_hash": HASH_1,
    }]}

    exact = evaluate_catalog_business_governance(
        catalog, {}, business_review_lookup={(VERSION_GID, HASH_1): HASH_1},
    )
    stale = evaluate_catalog_business_governance(
        catalog, {}, business_review_lookup={(VERSION_GID, HASH_2): HASH_2},
    )

    assert exact.status == "passed"
    assert exact.capabilities[0].approved_definition_hash == HASH_1
    assert stale.status == "blocked"
    assert stale.capabilities[0].human_approved is False


def test_release_gate_command_wires_explicit_exact_hash_approval_artifact(
    monkeypatch, tmp_path: Path, capsys,
):
    release_id = "rel_0123456789abcdef0123456789abcdef"
    release = tmp_path / "docs/governance/capability-catalog-release.json"
    release.parent.mkdir(parents=True)
    release.write_text(json.dumps({"release_id": release_id}), encoding="utf-8")
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({
        "schema_version": 1, "catalog_release_id": release_id,
        "approvals": [{
            "capability_key": "person.height.write@1",
            "capability_version_gid": VERSION_GID,
            "definition_hash": HASH_1, "decision": "approved",
        }],
    }), encoding="utf-8")
    captured = {}

    def evaluate(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(passed=True, serialized=lambda: {"passed": True})

    monkeypatch.setattr(release_gate_command, "evaluate_release_gate", evaluate)
    monkeypatch.setattr("sys.argv", [
        "check_capability_v2_release_gate.py", "--root", str(tmp_path),
        "--web-root", str(tmp_path), "--business-approvals", str(approvals),
    ])

    assert release_gate_command.main() == 0
    assert json.loads(capsys.readouterr().out) == {"passed": True}
    assert captured["business_review_lookup"] == {(VERSION_GID, HASH_1): HASH_1}
