from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs/acceptance/agent-runtime-capability-closure.json"
NORMALIZED = ROOT / "docs/acceptance/agent-runtime-capability-closure.normalized.json"
IDENTITY = ROOT / "docs/acceptance/agent-runtime-capability-closure-evidence.json"
STRUCTURAL = ROOT / "docs/governance/craft-agent-project-structural-web-remediation.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_agent_closure_acceptance_binds_clean_commit_and_zero_remainder() -> None:
    from backend.scripts.run_capability_v2_acceptance import validate_report_schema

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    evidence = json.loads(IDENTITY.read_text(encoding="utf-8"))
    structural = json.loads(STRUCTURAL.read_text(encoding="utf-8"))

    assert validate_report_schema(report) == []
    assert report["status"] == "passed"
    assert report["working_tree_clean"] is True
    assert report["git_commit"] == "3bfbd3f6498364a248b6253e0362c3a087c6a1f4"
    assert report["cases"] == {
        "stable_capabilities": 479,
        "mandatory_case_types": 7,
        "declared_cases": 3353,
        "validated_cases": 3353,
        "failed": 0,
        "skipped": 0,
    }
    assert report["completion"]["failed"] == [
        "coverage_invariant:stable_functions:922!=920"
    ]
    assert evidence["acceptance_report_sha256"] == _sha256(REPORT)
    assert evidence["acceptance_report_id"] == report["report_id"]
    assert evidence["code_commit"] == report["git_commit"]
    assert evidence["provider_manifest_sha256"] == report["domain_manifest"]["sha256"]
    assert evidence["catalog_release"] == report["catalog_release"]
    assert evidence["backend_source_revision"] == (
        "d56c743dee03112b2a3211a4ccb659ebed9cfda5"
    )
    assert evidence["frontend_revision"] == (
        "08359de59e756ce73c61df9818c7e7bcaeb86975"
    )
    assert evidence["frontend_tree"] == "3c3156841af0d4bf2833dba8184b071265993965"
    assert evidence["structural_counts"] == structural["counts"] == {
        "groups": 14,
        "occurrences": 17,
        "migrated_groups": 9,
        "migrated_occurrences": 12,
        "removed_dead_entry_groups": 5,
        "removed_dead_entry_occurrences": 5,
        "unresolved_groups": 0,
        "unresolved_occurrences": 0,
    }
    assert evidence["closure_arithmetic"]["canonical_remainder"] == {
        "groups": 0,
        "occurrences": 0,
    }
    assert evidence["controlled_agent_mysql_oceanbase_gate"]["status"] == "pending"
    assert evidence["controlled_agent_mysql_oceanbase_gate"]["mandatory_probe_result"] == (
        "4 errors"
    )


def test_agent_closure_normalized_projection_reuses_established_framework() -> None:
    from backend.scripts.build_project_list_approval_acceptance_evidence import (
        normalize_acceptance_report,
        semantic_sha256,
    )

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    normalized = json.loads(NORMALIZED.read_text(encoding="utf-8"))
    evidence = json.loads(IDENTITY.read_text(encoding="utf-8"))

    assert normalized == normalize_acceptance_report(report)
    assert evidence["normalized_report_sha256"] == _sha256(NORMALIZED)
    assert evidence["normalized_semantic_sha256"] == semantic_sha256(normalized)
    assert evidence["normalized_semantic_sha256"] == evidence["normalized_report_sha256"]
