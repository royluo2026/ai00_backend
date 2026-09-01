from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.capability_governance_test.release_gate import ReleaseCandidate, ReleaseGate
from backend.capability_v2.catalog import build_catalog_entry, build_release, load_catalog_release
from backend.capability_v2.release_gate import (
    BusinessGovernanceConfigurationError,
    evaluate_catalog_business_governance,
    load_business_approval_artifact,
    load_legacy_baseline,
    parse_business_governance_result,
)
from backend.scripts.build_capability_v2_production_artifact import (
    _canonical_release_report,
    validate_release_report,
)
from backend.scripts import check_capability_v2_release_gate as release_gate_command


HASH_2 = "sha256:" + "2" * 64


def _trusted_catalog() -> dict[str, object]:
    source = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/governance/capability-catalog-release.json")
        .read_text(encoding="utf-8")
    )
    descriptor = load_catalog_release(source).descriptors[0]
    release = build_release((descriptor,), created_at=datetime(2026, 9, 1, tzinfo=UTC))
    document = release.model_dump(mode="json")
    document["descriptors"] = [build_catalog_entry(descriptor)]
    return document


TRUSTED_CATALOG = _trusted_catalog()
TRUSTED_ROW = TRUSTED_CATALOG["descriptors"][0]
HASH_1 = TRUSTED_ROW["business_definition_hash"]
VERSION_GID = TRUSTED_ROW["capability_version_gid"]
CAPABILITY_KEY = f"{TRUSTED_ROW['id']}@{TRUSTED_ROW['major_version']}"


def _governance(*, kind: str = "new", approved: bool = True):
    baseline = (
        {CAPABILITY_KEY: HASH_1 if kind == "unchanged_legacy" else HASH_2}
        if kind != "new" else {}
    )
    approvals = {(VERSION_GID, HASH_1): HASH_1} if approved else {}
    return evaluate_catalog_business_governance(
        TRUSTED_CATALOG, baseline, business_review_lookup=approvals,
    )


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
        parse_business_governance_result(
            document, expected_catalog=TRUSTED_CATALOG, legacy_baseline={},
            business_review_lookup={(VERSION_GID, HASH_1): HASH_1},
        )


def test_canonical_governance_parser_rederives_the_exact_valid_result():
    expected = _governance(kind="unchanged_legacy", approved=False)

    context = {
        "expected_catalog": TRUSTED_CATALOG,
        "legacy_baseline": {CAPABILITY_KEY: HASH_1},
        "business_review_lookup": {},
    }
    assert parse_business_governance_result(expected, **context) == expected
    assert parse_business_governance_result(expected.serialized(), **context) == expected


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
        ReleaseCandidate("rev-a", TRUSTED_CATALOG["release_id"], 101, 201),
        test_status="passed", approvals_complete=True, data_complete=True,
        evidence_hash=HASH_1, static_gate_status="passed", static_gate_hash=HASH_2,
        business_governance=_governance(), business_catalog=TRUSTED_CATALOG,
        legacy_baseline={}, business_review_lookup={(VERSION_GID, HASH_1): HASH_1},
        idempotency_key="signed-valid",
    ).to_document()
    report["business_governance"]["capabilities"][0]["human_approved"] = False
    canonical = _canonical_release_report(report)
    report["report_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    report["signature"] = base64.b64encode(private_key.sign(canonical)).decode("ascii")
    path = tmp_path / "tampered-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    assert "release_report_governance_invalid" in validate_release_report(
        path, {"release-test": public_key}, expected_catalog=TRUSTED_CATALOG,
        legacy_baseline={}, business_review_lookup={(VERSION_GID, HASH_1): HASH_1},
    )


def test_signed_gate_fails_closed_without_trusted_catalog_and_approval_context():
    report = ReleaseGate(
        next_gid=iter(range(601, 610)).__next__, signer=lambda _payload: "signature",
    ).evaluate(
        ReleaseCandidate("rev-a", TRUSTED_CATALOG["release_id"], 101, 201),
        test_status="passed", approvals_complete=True, data_complete=True,
        evidence_hash=HASH_1, static_gate_status="passed", static_gate_hash=HASH_2,
        business_governance=_governance(), idempotency_key="missing-trusted-context",
    )

    assert report.conclusion == "fail"
    assert "business_governance_missing" in report.blockers


def _catalog(path: Path) -> dict:
    source = Path(__file__).resolve().parents[2] / "docs/governance/capability-catalog-release.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def test_baseline_verification_is_bound_to_the_referenced_catalog():
    root = Path(__file__).resolve().parents[2]
    baseline = load_legacy_baseline(
        root / "docs/governance/capability-business-governance-legacy-baseline.json",
        repository_root=root,
    )

    assert baseline.catalog_release_id == "rel_0b584b19349bc98727900583bb19f687"
    assert baseline.projection_hash == "sha256:15630f67419ab2c37da05b21be35505a030fd64ea5ef0a8e47d4ad81d0fa139d"


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
    catalog = TRUSTED_CATALOG

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
