from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/check_structural_remediation_plan.py"


def _module():
    spec = importlib.util.spec_from_file_location("structural_remediation_plan", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_preserves_historical_scope_and_records_current_migration_progress():
    """Breaks if a completed owner-service group disappears instead of being marked migrated."""
    module = _module()
    payload = module.load_plan(ROOT / "docs/governance/capability-v2-structural-remediation-plan.json")

    assert module.validate_plan(ROOT, payload) == ()
    assert payload["counts"] == {"groups": 37, "occurrences": 45}
    plugin_install = next(
        group for group in payload["groups"]
        if group["group_id"] == "POST /api/plugin/install"
    )
    assert plugin_install["current_status"] == "migrated"
    assert plugin_install["current_disposition"] == "migrated"
    assert plugin_install["current_evidence"]["target_capability"] == (
        "base.plugin.installation.request.create@1"
    )


def test_plan_validator_rejects_missing_occurrence_identity():
    """Breaks if a plan group can omit a source occurrence while retaining its route."""
    module = _module()
    payload = module.load_plan(ROOT / "docs/governance/capability-v2-structural-remediation-plan.json")
    mutated = copy.deepcopy(payload)
    mutated["groups"][0]["occurrences"].pop()

    assert "occurrence_identity_mismatch" in module.validate_plan(ROOT, mutated)


def test_plan_validator_rejects_owner_service_substitution():
    """Breaks if a route-shaped adapter can replace its reviewed owner service."""
    module = _module()
    payload = module.load_plan(ROOT / "docs/governance/capability-v2-structural-remediation-plan.json")
    mutated = copy.deepcopy(payload)
    mutated["groups"][0]["owner_service"] = "forged.route_adapter"

    assert "owner_service_mismatch" in module.validate_plan(ROOT, mutated)


def test_project_owner_service_is_real_and_rejects_a_fabricated_source_path():
    """Breaks if a plan names a Project service outside the real Project Management package."""
    module = _module()
    payload = module.load_plan(ROOT / "docs/governance/capability-v2-structural-remediation-plan.json")
    project_group = next(
        group for group in payload["groups"]
        if group["group_id"] == "POST /api/approval/orders/{dynamic}/reject"
    )

    assert project_group.get("owner_service") == (
        "plugins.project_management.project_management_backend.application.service.ProjectManagementApplication"
    )
    assert project_group.get("owner_service_source") == (
        "plugins/project_management/project_management_backend/application/service.py"
    )
    assert (ROOT / project_group["owner_service_source"]).is_file()

    mutated = copy.deepcopy(payload)
    next(group for group in mutated["groups"] if group["group_id"] == project_group["group_id"])["owner_service_source"] = (
        "plugins/project/project_backend/application/approval_service.py"
    )
    assert "owner_service_source_missing" in module.validate_plan(ROOT, mutated)

    next(group for group in mutated["groups"] if group["group_id"] == project_group["group_id"])["owner_service_source"] = (
        "plugins/craft/craft_backend/application/rules.py"
    )
    assert "owner_service_source_mismatch" in module.validate_plan(ROOT, mutated)


def test_plan_validator_rejects_operations_or_bff_reclassification():
    """Breaks if an unresolved business route is hidden as an operations or BFF exemption."""
    module = _module()
    payload = module.load_plan(ROOT / "docs/governance/capability-v2-structural-remediation-plan.json")
    for disposition in ("operations_excluded", "bff"):
        mutated = copy.deepcopy(payload)
        mutated["groups"][0]["implementation_disposition"] = disposition
        assert "forbidden_disposition" in module.validate_plan(ROOT, mutated)
