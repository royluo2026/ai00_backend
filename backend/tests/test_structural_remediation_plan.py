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


def test_plan_reconciles_the_fresh_final_unresolved_occurrence_identities():
    """Breaks if an unresolved source occurrence can disappear from the execution plan."""
    module = _module()
    payload = module.load_plan(ROOT / "docs/governance/capability-v2-structural-remediation-plan.json")

    assert module.validate_plan(ROOT, payload) == ()
    assert payload["counts"] == {"groups": 37, "occurrences": 45}


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


def test_plan_validator_rejects_operations_or_bff_reclassification():
    """Breaks if an unresolved business route is hidden as an operations or BFF exemption."""
    module = _module()
    payload = module.load_plan(ROOT / "docs/governance/capability-v2-structural-remediation-plan.json")
    for disposition in ("operations_excluded", "bff"):
        mutated = copy.deepcopy(payload)
        mutated["groups"][0]["implementation_disposition"] = disposition
        assert "forbidden_disposition" in module.validate_plan(ROOT, mutated)
