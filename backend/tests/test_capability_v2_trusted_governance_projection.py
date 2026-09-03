from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import base64
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import backend.capability_v2.release_gate as release_gate_module
import backend.scripts.build_capability_v2_production_artifact as artifact_builder
from backend.scripts import check_capability_v2_release_gate as release_gate_command
from backend.capability_governance_test.release_gate import ReleaseCandidate, ReleaseGate
from backend.capability_v2.catalog import build_catalog_entry, build_release, load_catalog_release
from backend.capability_v2.contracts import LifecycleStatus
from backend.capability_v2.release_gate import (
    BusinessGateCapability,
    BusinessGovernanceConfigurationError,
    build_business_catalog_projection,
    create_legacy_baseline,
    evaluate_business_governance_gate,
    evaluate_catalog_business_governance,
    load_legacy_baseline,
    parse_business_governance_result,
)


ROOT = Path(__file__).resolve().parents[2]


def _catalog(*, count: int = 1, changed_first: bool = False) -> dict[str, object]:
    source = json.loads(
        (ROOT / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    descriptors = [
        item.model_copy(update={
            "business_effect": f"Operators receive the governed {item.id} business result.",
            "business_acceptance_criteria": (
                "A successful invocation returns the declared schema-valid business result.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": (
                "No additional domain invariant applies beyond the declared contract."
            ),
        })
        for item in load_catalog_release(source).descriptors[:count]
    ]
    if changed_first:
        descriptors[0] = descriptors[0].model_copy(
            update={"business_effect": descriptors[0].business_effect + " Materially changed."}
        )
    release = build_release(descriptors, created_at=datetime(2026, 9, 1, tzinfo=UTC))
    document = release.model_dump(mode="json")
    document["descriptors"] = [build_catalog_entry(item) for item in release.descriptors]
    return document


def _incomplete_catalog(kind: str) -> dict[str, object]:
    source = _catalog()
    descriptor = load_catalog_release(source).descriptors[0]
    updates: dict[str, object] = {
        "business_effect": "Operators receive one governed business result.",
        "business_acceptance_criteria": (
            "A successful invocation returns the declared business result.",
        ),
        "business_invariants": (),
        "no_business_invariant_reason": (
            "No additional domain invariant applies beyond the declared contract."
        ),
    }
    if kind == "all_empty":
        updates.update(
            business_effect="", business_acceptance_criteria=(),
            no_business_invariant_reason=None,
        )
    elif kind == "purpose_only":
        updates.update(business_acceptance_criteria=())
    elif kind == "invalid_acceptance":
        updates.update(business_acceptance_criteria=("   ",))
    elif kind == "missing_invariant_declaration":
        updates.update(no_business_invariant_reason=None)
    else:  # pragma: no cover - the parameter list below is closed
        raise AssertionError(kind)
    descriptor = descriptor.model_copy(update=updates)
    release = build_release((descriptor,), created_at=datetime(2026, 9, 2, tzinfo=UTC))
    document = release.model_dump(mode="json")
    document["descriptors"] = [build_catalog_entry(descriptor)]
    return document


def _mixed_lifecycle_catalog() -> dict[str, object]:
    descriptors = list(load_catalog_release(_catalog(count=2)).descriptors)
    descriptors[1] = descriptors[1].model_copy(update={
        "business_effect": "",
        "business_acceptance_criteria": (),
        "business_invariants": (),
        "no_business_invariant_reason": None,
    })
    release = build_release(descriptors, created_at=datetime(2026, 9, 2, tzinfo=UTC))
    document = release.model_dump(mode="json")
    document["descriptors"] = [build_catalog_entry(item) for item in release.descriptors]
    document["descriptors"][1]["lifecycle_status"] = LifecycleStatus.STABLE
    return document


def _mixed_lifecycle_case(
    change_kind: str,
) -> tuple[dict[str, object], dict[str, str], dict[tuple[str, str], str]]:
    catalog = _mixed_lifecycle_catalog()
    valid, incomplete = catalog["descriptors"]
    valid_key = f"{valid['id']}@{valid['major_version']}"
    incomplete_key = f"{incomplete['id']}@{incomplete['major_version']}"
    baseline = {valid_key: valid["business_definition_hash"]}
    if change_kind == "material_change":
        baseline[incomplete_key] = "sha256:" + "f" * 64
    approvals = {
        (incomplete["capability_version_gid"], incomplete["business_definition_hash"]):
            incomplete["business_definition_hash"]
    }
    return catalog, baseline, approvals


INCOMPLETE_DEFINITIONS = (
    "all_empty", "purpose_only", "invalid_acceptance", "missing_invariant_declaration",
)


def _approval_lookup(catalog: dict[str, object]) -> dict[tuple[str, str], str]:
    return {
        (str(row["capability_version_gid"]), str(row["business_definition_hash"])):
            str(row["business_definition_hash"])
        for row in catalog["descriptors"]
    }


def _baseline_hash(document: dict[str, object]) -> str:
    payload = {
        key: document[key]
        for key in (
            "schema_version", "source_revision", "catalog_release_id",
            "catalog_hash", "projection_hash", "capabilities",
        )
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git_repository(tmp_path: Path, catalog: dict[str, object]) -> tuple[Path, Path, str]:
    repository = tmp_path / "repository"
    catalog_path = repository / "docs/governance/capability-catalog-release.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    for args in (
        ("init",),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
        ("add", "."),
        ("commit", "-m", "catalog cutover"),
    ):
        subprocess.run(("git", *args), cwd=repository, check=True, capture_output=True)
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=repository, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    return repository, catalog_path, revision


def test_governance_parser_binds_rows_and_approval_to_trusted_catalog_projection():
    catalog = _catalog(count=2)
    projection = build_business_catalog_projection(catalog)
    result = evaluate_catalog_business_governance(
        catalog, {}, business_review_lookup=_approval_lookup(catalog),
    )

    assert result.catalog_binding == projection.binding
    assert parse_business_governance_result(
        result.serialized(), expected_catalog=catalog, legacy_baseline={},
        business_review_lookup=_approval_lookup(catalog),
    ) == result

    for mutation in ("fake", "omitted", "extra", "self_approved"):
        document = deepcopy(result.serialized())
        if mutation == "fake":
            document["capabilities"][0]["capability_key"] = "invented.capability@1"
        elif mutation == "omitted":
            document["capabilities"].pop()
        elif mutation == "extra":
            document["capabilities"].append(deepcopy(document["capabilities"][0]))
            document["capabilities"][-1]["capability_key"] = "invented.capability@1"
        with pytest.raises(BusinessGovernanceConfigurationError, match="business_governance_invalid"):
            parse_business_governance_result(
                document, expected_catalog=catalog, legacy_baseline={},
                business_review_lookup={} if mutation == "self_approved" else _approval_lookup(catalog),
            )


def test_baseline_verifies_historical_catalog_while_current_changes_are_classified(tmp_path: Path):
    original = _catalog()
    repository, catalog_path, revision = _git_repository(tmp_path, original)
    baseline_path = repository / "docs/governance/baseline.json"

    created = create_legacy_baseline(catalog_path, baseline_path, source_revision="HEAD")
    changed = _catalog(changed_first=True)
    catalog_path.write_text(json.dumps(changed), encoding="utf-8")
    loaded = load_legacy_baseline(baseline_path)
    result = evaluate_catalog_business_governance(changed, loaded.capabilities)

    assert created.source_revision == revision
    assert loaded == created
    assert result.capabilities[0].change_kind == "material_change"
    assert result.status == "blocked"


def test_baseline_rejects_tampered_historical_provenance_and_nonexistent_revision(tmp_path: Path):
    catalog = _catalog()
    repository, catalog_path, _revision = _git_repository(tmp_path, catalog)
    baseline_path = repository / "docs/governance/baseline.json"
    create_legacy_baseline(catalog_path, baseline_path, source_revision="HEAD")
    document = json.loads(baseline_path.read_text(encoding="utf-8"))
    document["catalog_release_id"] = "rel_" + "f" * 32
    document["baseline_hash"] = _baseline_hash(document)
    baseline_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(BusinessGovernanceConfigurationError, match="legacy_baseline_catalog_mismatch"):
        load_legacy_baseline(baseline_path)
    with pytest.raises(BusinessGovernanceConfigurationError, match="legacy_baseline_source_revision_invalid"):
        create_legacy_baseline(
            catalog_path, repository / "docs/governance/missing.json",
            source_revision="does-not-exist",
        )


def test_business_catalog_projection_rejects_non_business_or_empty_catalog():
    with pytest.raises(BusinessGovernanceConfigurationError, match="business_catalog_invalid"):
        build_business_catalog_projection({"release_id": "rel_fake", "descriptors": []})
    with pytest.raises(BusinessGovernanceConfigurationError, match="business_catalog_invalid"):
        evaluate_catalog_business_governance({"capabilities": []}, {})


@pytest.mark.parametrize("kind", INCOMPLETE_DEFINITIONS)
def test_projection_rejects_exact_hash_nonlegacy_incomplete_business_definition(kind: str):
    catalog = _incomplete_catalog(kind)

    with pytest.raises(
        BusinessGovernanceConfigurationError,
        match="business_catalog_definition_invalid",
    ):
        build_business_catalog_projection(catalog, legacy_baseline={})


@pytest.mark.parametrize("kind", INCOMPLETE_DEFINITIONS)
def test_analysis_mode_reports_exact_nonlegacy_definition_blockers(kind: str):
    catalog = _incomplete_catalog(kind)
    row = catalog["descriptors"][0]
    key = f"{row['id']}@{row['major_version']}"

    result = evaluate_catalog_business_governance(
        catalog, {}, report_definition_blockers=True,
    )

    assert result.status == "blocked"
    assert result.machine_passed is False
    assert result.capabilities[0].capability_key == key
    assert all(blocker.endswith(f":{key}") for blocker in result.capabilities[0].blockers)
    assert f"business_definition_approval_missing:{key}" in result.capabilities[0].blockers


def test_projection_normalizes_json_and_enum_lifecycle_values():
    json_catalog = _catalog(count=2)
    enum_catalog = deepcopy(json_catalog)
    for row in enum_catalog["descriptors"]:
        row["lifecycle_status"] = LifecycleStatus(row["lifecycle_status"])

    json_projection = build_business_catalog_projection(json_catalog, legacy_baseline={})
    enum_projection = build_business_catalog_projection(enum_catalog, legacy_baseline={})

    assert enum_projection == json_projection
    assert enum_projection.binding == json_projection.binding


@pytest.mark.parametrize("change_kind", ("new", "material_change"))
def test_core_rejects_enum_stable_incomplete_definition_in_mixed_catalog(change_kind: str):
    catalog, baseline, approvals = _mixed_lifecycle_case(change_kind)

    with pytest.raises(
        BusinessGovernanceConfigurationError,
        match="business_catalog_definition_invalid",
    ):
        evaluate_catalog_business_governance(
            catalog, baseline, business_review_lookup=approvals,
        )


@pytest.mark.parametrize("change_kind", ("new", "material_change"))
def test_signed_release_gate_fails_closed_for_enum_stable_incomplete_definition(
    change_kind: str,
):
    catalog, baseline, approvals = _mixed_lifecycle_case(change_kind)
    valid, incomplete = catalog["descriptors"]
    projection = build_business_catalog_projection(catalog, legacy_baseline={
        f"{row['id']}@{row['major_version']}": row["business_definition_hash"]
        for row in catalog["descriptors"]
    })
    governance = evaluate_business_governance_gate((
        BusinessGateCapability(
            capability_key=f"{valid['id']}@{valid['major_version']}",
            capability_version_gid=valid["capability_version_gid"],
            definition_hash=valid["business_definition_hash"],
            approved_definition_hash=None,
            change_kind="unchanged_legacy",
            human_approved=False,
            runtime_verified=False,
        ),
        BusinessGateCapability(
            capability_key=f"{incomplete['id']}@{incomplete['major_version']}",
            capability_version_gid=incomplete["capability_version_gid"],
            definition_hash=incomplete["business_definition_hash"],
            approved_definition_hash=incomplete["business_definition_hash"],
            change_kind=change_kind,
            human_approved=True,
            runtime_verified=True,
        ),
    ), catalog_binding=projection.binding)

    gate_inputs = {}
    if "static_gate_status" in inspect.signature(ReleaseGate.evaluate).parameters:
        gate_inputs.update(
            static_gate_status="passed",
            static_gate_hash="sha256:static-gate",
        )
    report = ReleaseGate(
        next_gid=iter((1,)).__next__, signer=lambda _payload: "signature:test",
    ).evaluate(
        ReleaseCandidate("rev-a", catalog["release_id"], 101, 201),
        test_status="passed",
        approvals_complete=True,
        data_complete=True,
        evidence_hash="sha256:evidence",
        business_governance=governance,
        business_catalog=catalog,
        legacy_baseline=baseline,
        business_review_lookup=approvals,
        idempotency_key=f"mixed-lifecycle-{change_kind}",
        **gate_inputs,
    )

    assert report.conclusion == "fail"
    assert "business_governance_missing" in report.blockers
    assert report.signature == "signature:test"


def test_enum_stable_legacy_exemption_requires_exact_key_and_hash():
    catalog = _mixed_lifecycle_catalog()
    incomplete = catalog["descriptors"][1]
    key = f"{incomplete['id']}@{incomplete['major_version']}"
    digest = incomplete["business_definition_hash"]

    for baseline in (
        {"wrong.capability@1": digest},
        {key: "sha256:" + "f" * 64},
    ):
        with pytest.raises(
            BusinessGovernanceConfigurationError,
            match="business_catalog_definition_invalid",
        ):
            build_business_catalog_projection(catalog, legacy_baseline=baseline)

    assert build_business_catalog_projection(
        catalog, legacy_baseline={key: digest},
    ).capabilities[1].business_definition_hash == digest


def test_projection_accepts_exact_historical_cutover_catalog_as_legacy():
    baseline_path = ROOT / "docs/governance/capability-business-governance-legacy-baseline.json"
    baseline = load_legacy_baseline(baseline_path, repository_root=ROOT)
    historical = subprocess.run(
        (
            "git", "show",
            f"{baseline.source_revision}:docs/governance/capability-catalog-release.json",
        ),
        cwd=ROOT, check=True, capture_output=True,
    )
    catalog = json.loads(historical.stdout.decode("utf-8"))

    projection = build_business_catalog_projection(
        catalog, legacy_baseline=baseline.capabilities,
    )

    assert len(projection.capabilities) == 495


@pytest.mark.parametrize("kind", INCOMPLETE_DEFINITIONS)
def test_official_command_fails_closed_for_exact_hash_incomplete_business_definition(
    kind: str, tmp_path: Path, monkeypatch,
):
    original = _catalog()
    repository, business_catalog_path, _revision = _git_repository(tmp_path, original)
    baseline_path = repository / "docs/governance/baseline.json"
    create_legacy_baseline(business_catalog_path, baseline_path, source_revision="HEAD")
    incomplete = _incomplete_catalog(kind)
    business_catalog_path.write_text(json.dumps(incomplete), encoding="utf-8")
    static_catalog_path = repository / "docs/capabilities/catalog.v2.json"
    static_catalog_path.parent.mkdir(parents=True)
    static_catalog_path.write_text(json.dumps({"capabilities": []}), encoding="utf-8")
    atomicity_path = repository / "docs/governance/capability-atomicity-dispositions.json"
    atomicity_path.write_text("{}", encoding="utf-8")
    row = incomplete["descriptors"][0]
    approval_path = repository / "approvals.json"
    approval_path.write_text(json.dumps({
        "schema_version": 1,
        "catalog_release_id": incomplete["release_id"],
        "approvals": [{
            "capability_key": f"{row['id']}@{row['major_version']}",
            "capability_version_gid": row["capability_version_gid"],
            "definition_hash": row["business_definition_hash"],
            "decision": "approved",
        }],
    }), encoding="utf-8")
    _stub_non_business_gate(monkeypatch)

    monkeypatch.setattr(sys, "argv", [
        "check_capability_v2_release_gate.py",
        "--root", str(repository),
        "--web-root", str(repository),
        "--catalog", str(static_catalog_path),
        "--legacy-baseline", str(baseline_path),
        "--business-approvals", str(approval_path),
    ])

    with pytest.raises(
        BusinessGovernanceConfigurationError,
        match="business_catalog_definition_invalid",
    ):
        release_gate_command.main()


@pytest.mark.parametrize("kind", INCOMPLETE_DEFINITIONS)
def test_production_consumer_rejects_signed_exact_hash_incomplete_business_definition(
    kind: str, tmp_path: Path,
):
    catalog = _incomplete_catalog(kind)
    row = catalog["descriptors"][0]
    key = f"{row['id']}@{row['major_version']}"
    legacy = {key: row["business_definition_hash"]}
    approvals = {
        (row["capability_version_gid"], row["business_definition_hash"]):
            row["business_definition_hash"]
    }
    projection = build_business_catalog_projection(catalog, legacy_baseline=legacy)
    governance = evaluate_business_governance_gate((BusinessGateCapability(
        capability_key=key,
        capability_version_gid=row["capability_version_gid"],
        definition_hash=row["business_definition_hash"],
        approved_definition_hash=row["business_definition_hash"],
        change_kind="unchanged_legacy",
        human_approved=True,
        runtime_verified=True,
    ),), catalog_binding=projection.binding).serialized()
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    report = {
        "report_gid": "501", "code_revision": "rev-a",
        "product_catalog_release_id": catalog["release_id"],
        "snapshot_gid": "101", "test_run_gid": "201", "conclusion": "pass",
        "blockers": [], "evidence_hash": "sha256:evidence",
        "static_gate_hash": "sha256:static-gate",
        "business_governance": governance, "signing_key_id": "release-test",
    }
    canonical = artifact_builder._canonical_release_report(report)
    report["report_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    report["signature"] = base64.b64encode(private_key.sign(canonical)).decode("ascii")
    report_path = tmp_path / "release-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    errors = artifact_builder.validate_release_report(
        report_path, {"release-test": public_key}, expected_catalog=catalog,
        legacy_baseline={}, business_review_lookup=approvals,
    )

    assert "release_report_governance_invalid" in errors


def _stub_non_business_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        release_gate_module, "evaluate_completion", lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        release_gate_module, "audit_catalog", lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        release_gate_module, "load_atomicity_dispositions",
        lambda *_args, **_kwargs: SimpleNamespace(dispositions=()),
    )
    monkeypatch.setattr(
        release_gate_module, "audit_generic_operations", lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        release_gate_module, "audit_orchestration_registry",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        release_gate_module, "CatalogTargetIndex",
        type("Index", (), {"from_catalog": staticmethod(lambda *_args, **_kwargs: object())}),
    )


def test_release_gate_classifies_current_catalog_independently_of_static_catalog(
    tmp_path: Path, monkeypatch,
):
    original = _catalog()
    repository, business_catalog_path, _revision = _git_repository(tmp_path, original)
    baseline_path = repository / "docs/governance/baseline.json"
    baseline = create_legacy_baseline(business_catalog_path, baseline_path, source_revision="HEAD")
    static_catalog_path = repository / "docs/capabilities/catalog.v2.json"
    static_catalog_path.parent.mkdir(parents=True)
    static_catalog_path.write_text(json.dumps({"capabilities": []}), encoding="utf-8")
    atomicity_path = repository / "docs/governance/atomicity.json"
    atomicity_path.write_text("{}", encoding="utf-8")
    _stub_non_business_gate(monkeypatch)

    changed = _catalog(changed_first=True)
    business_catalog_path.write_text(json.dumps(changed), encoding="utf-8")
    row = changed["descriptors"][0]
    exact = {(row["capability_version_gid"], row["business_definition_hash"]): row["business_definition_hash"]}
    stale = {(row["capability_version_gid"], original["descriptors"][0]["business_definition_hash"]): original["descriptors"][0]["business_definition_hash"]}

    blocked = release_gate_module.evaluate_release_gate(
        repository, web_root=repository, catalog_path=static_catalog_path,
        atomicity_path=atomicity_path, legacy_baseline_path=baseline_path,
        business_catalog_path=business_catalog_path,
    ).business_governance
    approved = release_gate_module.evaluate_release_gate(
        repository, web_root=repository, catalog_path=static_catalog_path,
        atomicity_path=atomicity_path, legacy_baseline_path=baseline_path,
        business_catalog_path=business_catalog_path, business_review_lookup=exact,
    ).business_governance
    stale_result = release_gate_module.evaluate_release_gate(
        repository, web_root=repository, catalog_path=static_catalog_path,
        atomicity_path=atomicity_path, legacy_baseline_path=baseline_path,
        business_catalog_path=business_catalog_path, business_review_lookup=stale,
    ).business_governance

    assert blocked.status == "blocked"
    assert blocked.capabilities[0].change_kind == "material_change"
    assert approved.status == "passed"
    assert stale_result.status == "blocked"
    assert baseline.catalog_release_id != changed["release_id"]

    added = _catalog(count=2)
    business_catalog_path.write_text(json.dumps(added), encoding="utf-8")
    new_row = added["descriptors"][1]
    new_approval = {
        (new_row["capability_version_gid"], new_row["business_definition_hash"]):
            new_row["business_definition_hash"]
    }
    added_blocked = release_gate_module.evaluate_release_gate(
        repository, web_root=repository, catalog_path=static_catalog_path,
        atomicity_path=atomicity_path, legacy_baseline_path=baseline_path,
        business_catalog_path=business_catalog_path,
    ).business_governance
    added_approved = release_gate_module.evaluate_release_gate(
        repository, web_root=repository, catalog_path=static_catalog_path,
        atomicity_path=atomicity_path, legacy_baseline_path=baseline_path,
        business_catalog_path=business_catalog_path, business_review_lookup=new_approval,
    ).business_governance

    assert added_blocked.status == "blocked"
    assert added_blocked.capabilities[1].change_kind == "new"
    assert added_approved.status == "passed_with_legacy_backlog"
    assert added_approved.capabilities[1].governance_status == "passed"


def test_release_gate_rejects_non_business_catalog_at_governance_boundary(
    tmp_path: Path, monkeypatch,
):
    original = _catalog()
    repository, business_catalog_path, _revision = _git_repository(tmp_path, original)
    baseline_path = repository / "docs/governance/baseline.json"
    create_legacy_baseline(business_catalog_path, baseline_path, source_revision="HEAD")
    static_catalog_path = repository / "catalog.json"
    static_catalog_path.write_text(json.dumps({"capabilities": []}), encoding="utf-8")
    atomicity_path = repository / "atomicity.json"
    atomicity_path.write_text("{}", encoding="utf-8")
    _stub_non_business_gate(monkeypatch)

    with pytest.raises(BusinessGovernanceConfigurationError, match="business_catalog_invalid"):
        release_gate_module.evaluate_release_gate(
            repository, web_root=repository, catalog_path=static_catalog_path,
            atomicity_path=atomicity_path, legacy_baseline_path=baseline_path,
            business_catalog_path=static_catalog_path,
        )
