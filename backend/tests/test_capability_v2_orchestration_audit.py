from __future__ import annotations

import json
from pathlib import Path

from backend.capability_v2.catalog_targets import CatalogTargetIndex
from backend.capability_v2.orchestration_audit import audit_orchestration_registry


def test_orchestration_registry_audit_requires_catalog_capability(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "registry_kind": "task_tool",
        "entries": [{"task_id": "task-1", "capability_id": "base.missing", "owner_domain": "base"}],
    }), encoding="utf-8")

    report = audit_orchestration_registry(registry, {"capabilities": [{"id": "base.present"}]})

    assert report.missing_capabilities == ("task-1:base.missing",)
    assert report.serialized()["target_failures"] == [{
        "entry_key": "task-1",
        "reason_code": "target_missing",
        "capability_id": "base.missing",
        "major_version": 1,
    }]
    assert report.passed is False


def test_current_orchestration_registries_are_bound() -> None:
    import json as _json
    catalog = _json.loads(Path("docs/capabilities/catalog.v2.json").read_text(encoding="utf-8"))
    for name in ("task_tool_registry.json", "bff_capability_registry.json", "business_capability_ledger.json"):
        assert audit_orchestration_registry(Path("docs/governance") / name, catalog).passed


def test_orchestration_registry_reports_non_stable_target(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "registry_kind": "task_tool",
        "entries": [{"task_id": "task-1", "capability_id": "base.old", "owner_domain": "base"}],
    }), encoding="utf-8")
    catalog_index = CatalogTargetIndex.from_catalog({"capabilities": [{
        "id": "base.old", "major_version": 1,
        "lifecycle_status": "deprecated", "owner_domain": "base",
    }]})

    report = audit_orchestration_registry(registry, catalog_index)

    assert report.target_failures[0].reason_code == "target_not_stable"
    assert report.target_failures[0].entry_key == "task-1"
