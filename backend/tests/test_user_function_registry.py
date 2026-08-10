from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPOSITORY_ROOT / "docs" / "governance" / "user-function-registry.json"
SCRIPT_PATH = REPOSITORY_ROOT / "backend" / "scripts" / "build_user_function_registry.py"


def _builder_module():
    spec = importlib.util.spec_from_file_location("build_user_function_registry", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registry():
    return list(json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["functions"].values())


def test_every_stable_user_function_has_capability_or_valid_exclusion(registry):
    invalid = [row["function_id"] for row in registry
               if row["stability"] == "stable"
               and not row.get("target_capability")
               and row.get("classification") not in {"internal", "operations", "ui_transient"}]
    assert invalid == []


def test_merge_discovery_preserves_reviewed_governance_fields():
    builder = _builder_module()
    existing = {
        "rest:GET:/api/example": {
            "function_id": "rest:GET:/api/example",
            "domain": "Base",
            "stability": "stable",
            "current_consumers": ["REST"],
            "target_capability": "base.project.search",
            "exposure": "Web/REST",
            "automation_level": "interactive",
            "resource_types": ["project"],
            "data_classification": "internal",
            "classification": "mapped",
            "migration_status": "migrated",
            "owner": "Platform",
            "exclusion_reason": None,
            "review_note": "Approved for the first wave."
        }
    }
    discovered = [{
        "function_id": "rest:GET:/api/example",
        "domain": "Base",
        "stability": "stable",
        "current_consumers": ["REST", "Web"],
        "source_paths": ["backend/routers/example.py"]
    }]

    merged = builder.merge_discovery(existing, discovered)

    assert merged == [{
        **existing["rest:GET:/api/example"],
        "current_consumers": ["REST", "Web"],
        "source_paths": ["backend/routers/example.py"]
    }]


def test_check_reports_missing_stable_function():
    builder = _builder_module()

    errors = builder.registry_errors({}, [{
        "function_id": "rest:GET:/api/example",
        "domain": "Base",
        "stability": "stable",
        "current_consumers": ["REST"],
        "source_paths": ["backend/routers/example.py"]
    }])

    assert errors == ["missing stable function: rest:GET:/api/example"]
