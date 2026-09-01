from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import backend.capability_v2.release_gate as release_gate_module
from backend.capability_v2.catalog import build_catalog_entry, build_release, load_catalog_release
from backend.capability_v2.release_gate import (
    BusinessGovernanceConfigurationError,
    build_business_catalog_projection,
    create_legacy_baseline,
    evaluate_catalog_business_governance,
    load_legacy_baseline,
    parse_business_governance_result,
)


ROOT = Path(__file__).resolve().parents[2]


def _catalog(*, count: int = 1, changed_first: bool = False) -> dict[str, object]:
    source = json.loads(
        (ROOT / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    descriptors = list(load_catalog_release(source).descriptors[:count])
    if changed_first:
        descriptors[0] = descriptors[0].model_copy(
            update={"business_effect": descriptors[0].business_effect + " Materially changed."}
        )
    release = build_release(descriptors, created_at=datetime(2026, 9, 1, tzinfo=UTC))
    document = release.model_dump(mode="json")
    document["descriptors"] = [build_catalog_entry(item) for item in release.descriptors]
    return document


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
