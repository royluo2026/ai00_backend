from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FACTORY = ROOT / "backend/tests/support/integration_catalog_factory.py"
RESULT = ROOT / "docs/acceptance/project-list-approval-capability-closure.json"
IDENTITY = ROOT / "docs/acceptance/project-list-approval-capability-closure-evidence.json"
NORMALIZED = ROOT / "docs/acceptance/project-list-approval-capability-closure.normalized.json"


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
    from backend.scripts.run_capability_v2_acceptance import validate_report_schema

    assert evidence["adapter_factory"] == "backend.tests.support.integration_catalog_factory:build"
    assert evidence["factory_sha256"] == _sha256(FACTORY)
    assert evidence["acceptance_report_sha256"] == _sha256(RESULT)
    assert evidence["acceptance_report_id"] == report["report_id"]
    assert evidence["provider_manifest_sha256"] == report["domain_manifest"]["sha256"]
    assert evidence["code_commit"] == report["git_commit"]
    assert evidence["catalog_release"] == report["catalog_release"]
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


def test_normalized_acceptance_projection_is_replay_stable() -> None:
    """Breaks if host/time/temp-path noise changes the reproducible semantic identity."""
    from backend.scripts.build_project_list_approval_acceptance_evidence import (
        normalize_acceptance_report,
        semantic_sha256,
    )

    report = json.loads(RESULT.read_text(encoding="utf-8"))
    changed = json.loads(json.dumps(report))
    changed["generated_at"] = "2099-01-01T00:00:00Z"
    changed["environment_id"] = "different-host"
    changed["report_id"] = "sha256:" + "f" * 64
    changed["working_tree_clean"] = not report["working_tree_clean"]
    changed["test_run"]["command"] = ["C:/different/python.exe", "-m", "pytest"]
    changed["test_run"]["summary"] = "3311 passed in 999.99s"

    normalized = normalize_acceptance_report(report)
    assert normalize_acceptance_report(changed) == normalized
    assert json.loads(NORMALIZED.read_text(encoding="utf-8")) == normalized
    evidence = json.loads(IDENTITY.read_text(encoding="utf-8"))
    assert evidence["normalized_semantic_sha256"] == semantic_sha256(normalized)
    assert evidence["normalized_report_sha256"] == _sha256(NORMALIZED)
    assert "PYTHONPATH" in evidence["replay_command"]
    assert "AI00_INTEGRATION_ADAPTER_FACTORY" in evidence["replay_command"]

    changed = json.loads(json.dumps(report))
    changed["cases"]["validated_cases"] -= 1
    assert semantic_sha256(normalize_acceptance_report(changed)) != semantic_sha256(normalized)
