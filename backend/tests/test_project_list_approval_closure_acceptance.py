from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FACTORY = ROOT / "backend/tests/support/integration_catalog_factory.py"
RESULT = ROOT / "docs/acceptance/project-list-approval-capability-closure.json"
IDENTITY = ROOT / "docs/acceptance/project-list-approval-capability-closure-evidence.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_committed_integration_factory_is_loadable_and_valid(monkeypatch) -> None:
    """Breaks if clean-checkout Catalog generation loses its deterministic Integration wiring."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/integration"))
    module = importlib.import_module("backend.tests.support.integration_catalog_factory")
    from integration_backend.capabilities.wiring import build_application

    adapters = module.build()

    assert build_application(lambda: adapters) is not None


def test_committed_acceptance_result_binds_factory_report_and_provider_identities() -> None:
    """Breaks if the frozen acceptance result or its clean-replay factory changes silently."""
    evidence = json.loads(IDENTITY.read_text(encoding="utf-8"))
    report = json.loads(RESULT.read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8"))
    from backend.scripts.run_capability_v2_acceptance import validate_report_schema

    assert evidence["adapter_factory"] == "backend.tests.support.integration_catalog_factory:build"
    assert evidence["factory_sha256"] == _sha256(FACTORY)
    assert evidence["acceptance_report_sha256"] == _sha256(RESULT)
    assert evidence["acceptance_report_id"] == report["report_id"]
    assert evidence["provider_manifest_sha256"] == report["domain_manifest"]["sha256"]
    assert evidence["code_commit"] == report["git_commit"]
    assert evidence["catalog_release"] == report["catalog_release"] == catalog["release_id"]
    assert report["status"] == "passed"
    assert report["working_tree_clean"] is True
    assert report["cases"] == {
        "stable_capabilities": 473,
        "mandatory_case_types": 7,
        "declared_cases": 3311,
        "validated_cases": 3311,
        "failed": 0,
        "skipped": 0,
    }
    assert report["completion"]["failed"] == [
        "coverage_invariant:stable_functions:922!=920"
    ]
    assert validate_report_schema(report) == []
