from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/build_craft_agent_project_structural_web_remediation.py"
WEB_ROOT = ROOT.parent / "workmanship-web-capability-governance"


def _module():
    spec = importlib.util.spec_from_file_location("craft_agent_project_structural_manifest", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest():
    """One fresh scanner pass keeps the independently runnable suite bounded."""
    module = _module()
    return module, module.build_manifest(WEB_ROOT)


def test_manifest_conserves_the_final_three_domain_scope_without_unsafe_migration(manifest):
    """Breaks if a name-matched provider turns the final unsafe routes into a capability."""
    _, payload = manifest

    assert payload["counts"] == {
        "groups": 14,
        "occurrences": 17,
        "migrated_groups": 0,
        "migrated_occurrences": 0,
        "unresolved_groups": 14,
        "unresolved_occurrences": 17,
    }
    assert {entry["owner_domain"] for entry in payload["entries"]} == {
        "craft", "agent", "project_management",
    }
    for entry in payload["entries"]:
        assert entry["final_disposition"] == "unresolved"
        assert entry["final_inventory_mapping"] == "unresolved"
        assert entry["non_equivalence"]


def test_manifest_preserves_agent_execution_and_bop_conditional_boundaries(manifest):
    """Breaks if executable Agent calls or BOP branches are relabeled as safe generic operations."""
    _, payload = manifest
    entries = {
        (entry["method"], entry["normalized_route"]): entry
        for entry in payload["entries"]
    }
    for key in (
        ("POST", "/api/flows/test-node"),
        ("POST", "/api/skills/canvas-options"),
        ("POST", "/api/skills/execute-canvas"),
        ("POST", "/api/skills/resume-canvas"),
    ):
        assert entries[key]["runtime_execution"] == "unresolved_no_bounded_runtime_service"
    for key in (("GET", "/api/lists"), ("DELETE", "/api/lists/{dynamic}")):
        entry = entries[key]
        assert entry["bop_conditional_branch"] is True
        assert entry["candidate_capability"] is None
        lifecycle = entry["lifecycle_evidence"]
        assert lifecycle["source"]["source_path"] == "plugins/craft/craft_backend/routers/lists.py"
        assert lifecycle["source"]["source_sha256"].startswith("sha256:")
        assert lifecycle["selector"] == 'item_type == "bop_version"'
        assert lifecycle["direct_sql"] is False
    assert entries[("GET", "/api/lists")]["lifecycle_evidence"]["capability_id"] == "craft.bop.version.list"
    delete = entries[("DELETE", "/api/lists/{dynamic}")]["lifecycle_evidence"]
    assert delete["capability_id"] == "craft.bop.version.archive"
    assert delete["expected_revision_required"] is True

    approval = entries[("POST", "/api/approval/orders/{dynamic}/reject")]["approval_reject_evidence"]
    assert approval["legacy_reject_route_registered"] is False
    assert approval["adapter_notification"]["anchor"]["source_sha256"].startswith("sha256:")
    assert approval["project_audit_policy"]["value"] == "standard"


def test_manifest_validator_rejects_tampered_provider_contract_and_final_occurrence(manifest):
    """Breaks if hand edits can erase owner-service, contract, or frontend identity evidence."""
    module, payload = manifest
    assert module.validate_manifest_against_expected(payload, payload) == ()

    mutations = (
        ("provider_hash_mismatch", ("DELETE", "/api/craft_lib/equipments/{dynamic}"), lambda entry: entry.__setitem__("provider_source_sha256", "sha256:" + "0" * 64)),
        ("non_equivalence_evidence_mismatch", ("DELETE", "/api/craft_lib/equipments/{dynamic}"), lambda entry: entry["non_equivalence"].__setitem__("input", "forged")),
        ("lifecycle_evidence_mismatch", ("GET", "/api/lists"), lambda entry: entry["lifecycle_evidence"]["source"].__setitem__("source_sha256", "sha256:" + "0" * 64)),
        ("approval_evidence_mismatch", ("POST", "/api/approval/orders/{dynamic}/reject"), lambda entry: entry["approval_reject_evidence"]["adapter_notification"]["anchor"].__setitem__("start_line", 999)),
    )
    for reason, key, mutate in mutations:
        changed = json.loads(json.dumps(payload))
        entry = next(item for item in changed["entries"] if (item["method"], item["normalized_route"]) == key)
        mutate(entry)
        assert reason in module.validate_manifest_against_expected(changed, payload)

    for field, value in (("occurrence_id", "forged"), ("source", "web/forged.js"), ("line", 999), ("column", 999), ("source_sha256", "0" * 64)):
        changed = json.loads(json.dumps(payload))
        changed["entries"][0]["final_occurrences"][0][field] = value
        assert "final_occurrence_mismatch" in module.validate_manifest_against_expected(changed, payload)
    for field in ("source_ledger_revision", "source_ledger_sha256"):
        changed = json.loads(json.dumps(payload))
        changed[field] = "forged"
        assert "source_ledger_evidence_mismatch" in module.validate_manifest_against_expected(changed, payload)
