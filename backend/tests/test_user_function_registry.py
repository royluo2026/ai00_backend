from __future__ import annotations

import json
import importlib.util
import copy
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPOSITORY_ROOT / "docs" / "governance" / "user-function-registry.json"
SCHEMA_PATH = REPOSITORY_ROOT / "docs" / "governance" / "user-function-registry.schema.json"
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


@pytest.fixture
def registry_document():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_every_stable_user_function_has_capability_or_valid_exclusion(registry):
    invalid = [row["function_id"] for row in registry
               if row["stability"] == "stable"
               and not row.get("target_capability")
               and row.get("classification") not in {
                   "internal", "operations", "ui_transient", "transport_adapter",
                   "unstable_product_surface", "unreviewed",
               }]
    assert invalid == []


def test_first_class_domains_include_independent_maintainer_boundaries():
    builder = _builder_module()

    assert set(builder.DOMAINS) == {
        "Base Platform",
        "Agent",
        "Craft",
        "Digital Model",
        "Project Management",
        "Simulation",
        "Ontology",
        "Knowledge",
        "Local Integration",
    }


def test_domain_classification_uses_business_owner_not_consumer_surface():
    builder = _builder_module()

    assert builder._domain(
        "agent_tool:get_bop_entries", "services/agent-runtime/src/tools.ts"
    ) == "Craft"
    assert builder._domain(
        "rest:POST:/api/agents/{agent_id}/runs", "backend/routers/agents.py"
    ) == "Agent"
    assert builder._domain(
        "rest:GET:/api/projects", "backend/routers/projects.py"
    ) == "Project Management"
    assert builder._domain(
        "rest:PATCH:/api/tasks/{task_id}", "backend/routers/tasks.py"
    ) == "Project Management"
    assert builder._domain(
        "agent_tool:create_task", "plugins/agent/agent_backend/ai_assistant/tool_registry.py"
    ) == "Project Management"
    assert builder._domain(
        "rest:GET:/api/ai/sessions", "plugins/agent/agent_backend/routers/ai_chat.py"
    ) == "Agent"
    assert builder._domain(
        "rest:GET:/api/health", "backend/routers/health.py"
    ) == "Base Platform"
    assert builder._domain(
        "capability:craft.gbop.item.knowledge.list",
        "plugins/craft/craft_backend/capabilities/gbop_read.py",
    ) == "Craft"


def test_registry_schema_exposes_every_independently_owned_domain():
    builder = _builder_module()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert set(schema["$defs"]["UserFunctionRecord"]["properties"]["domain"]["enum"]) == set(builder.DOMAINS)


def test_stable_unmapped_function_requires_specific_reviewed_exclusion():
    builder = _builder_module()
    row = {
        "function_id": "rest:GET:/api/example",
        "domain": "Base",
        "stability": "stable",
        "current_consumers": ["REST"],
        "target_capability": None,
        "classification": "operations",
        "exclusion_reason": builder.DEFAULT_EXCLUSION_REASON,
    }

    assert builder.registry_errors({row["function_id"]: row}, [row]) == [
        "stable function lacks a specific reviewed exclusion: rest:GET:/api/example"
    ]


def test_new_stable_discovery_remains_an_unreviewed_candidate():
    builder = _builder_module()
    discovered = [{
        "function_id": "rest:GET:/api/example",
        "domain": "Base",
        "stability": "stable",
        "current_consumers": ["REST"],
        "source_paths": ["backend/routers/example.py"],
    }]

    merged = builder.merge_discovery({}, discovered)

    assert merged[0]["classification"] == "unreviewed"
    assert merged[0]["migration_status"] == "candidate"
    assert merged[0]["exclusion_reason"] is None
    assert builder.registry_errors({merged[0]["function_id"]: merged[0]}, discovered) == [
        "stable function lacks capability or valid exclusion: rest:GET:/api/example"
    ]


def test_schema_validates_baseline_and_rejects_unknown_missing_and_invalid_exclusions(registry_document):
    builder = _builder_module()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert builder.validate_registry_document(registry_document, schema) == []

    unknown_root = copy.deepcopy(registry_document)
    unknown_root["unexpected"] = True
    assert "root has unknown property: unexpected" in builder.validate_registry_document(unknown_root, schema)

    relaxed_schema = copy.deepcopy(schema)
    relaxed_schema["additionalProperties"] = True
    assert builder.validate_registry_document(unknown_root, relaxed_schema) == []

    unknown_record = copy.deepcopy(registry_document)
    next(iter(unknown_record["functions"].values()))["unexpected"] = True
    assert "record has unknown property: unexpected" in builder.validate_registry_document(unknown_record, schema)

    missing_field = copy.deepcopy(registry_document)
    first_record = next(iter(missing_field["functions"].values()))
    del first_record["classification"]
    assert "record missing required property: classification" in builder.validate_registry_document(missing_field, schema)

    invalid_exclusion = copy.deepcopy(registry_document)
    candidate = next(row for row in invalid_exclusion["functions"].values() if row["target_capability"] is None)
    candidate.update({"classification": "operations", "migration_status": "excluded", "exclusion_reason": ""})
    assert "record has invalid exclusion" in builder.validate_registry_document(invalid_exclusion, schema)


def test_merge_discovery_preserves_reviewed_governance_fields():
    builder = _builder_module()
    existing = {
        "rest:GET:/api/example": {
            "function_id": "rest:GET:/api/example",
            "domain": "Base Platform",
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
            "review_notes": ["Approved for the first wave."]
        }
    }
    discovered = [{
        "function_id": "rest:GET:/api/example",
        "domain": "Base Platform",
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


def test_merge_migrates_retired_base_domain_without_losing_reviewed_governance():
    builder = _builder_module()
    existing = {
        "capability:base.project.search": {
            "function_id": "capability:base.project.search",
            "domain": "Base",
            "stability": "stable",
            "current_consumers": ["Capability"],
            "target_capability": "base.project.search",
            "exposure": "Capability",
            "automation_level": "automated",
            "resource_types": ["project"],
            "data_classification": "internal",
            "classification": "mapped",
            "migration_status": "registered",
            "owner": "Base",
            "exclusion_reason": None,
            "source_paths": ["backend/system_capabilities/base_provider.py"],
            "review_notes": ["Reviewed metadata must survive."],
        }
    }
    discovered = [{
        "function_id": "capability:base.project.search",
        "domain": "Project Management",
        "stability": "stable",
        "current_consumers": ["Capability"],
        "source_paths": ["backend/system_capabilities/base_provider.py"],
    }]

    row = builder.merge_discovery(existing, discovered)[0]

    assert row["domain"] == "Project Management"
    assert row["owner"] == "Project Management"
    assert row["review_notes"] == ["Reviewed metadata must survive."]


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


def test_check_reports_stale_ids_and_field_level_evidence_drift():
    builder = _builder_module()
    discovered = [{
        "function_id": "rest:GET:/api/example",
        "domain": "Base",
        "stability": "stable",
        "current_consumers": ["REST", "Web"],
        "source_paths": ["dist/web/example.js"],
    }]
    existing = builder.merge_discovery({}, discovered)[0]
    existing.update({
        "target_capability": "base.project.search",
        "classification": "mapped",
        "migration_status": "migrated",
        "current_consumers": ["REST"],
        "source_paths": ["backend/routers/example.py"],
        "domain": "Craft",
    })
    stale = {**existing, "function_id": "rest:GET:/api/stale"}

    errors = builder.registry_errors(
        {existing["function_id"]: existing, stale["function_id"]: stale}, discovered
    )

    assert errors == [
        "generated evidence drift for rest:GET:/api/example: current_consumers",
        "generated evidence drift for rest:GET:/api/example: domain",
        "generated evidence drift for rest:GET:/api/example: source_paths",
        "stale stable function: rest:GET:/api/stale",
    ]


def test_merge_discards_only_stale_unreviewed_generated_candidates():
    builder = _builder_module()
    discovered = [{
        "function_id": "web:/api/obsolete",
        "domain": "Base",
        "stability": "stable",
        "current_consumers": ["Web"],
        "source_paths": ["dist/web/obsolete.js"],
    }]
    generated = builder.merge_discovery({}, discovered)[0]

    assert builder.merge_discovery({generated["function_id"]: generated}, []) == []


def test_merge_discards_stale_unreviewed_capability_literals():
    builder = _builder_module()
    stale = {
        "function_id": "capability:craft.write",
        "domain": "Craft",
        "stability": "stable",
        "current_consumers": ["Capability Registry"],
        "target_capability": "craft.write",
        "classification": "mapped",
        "migration_status": "registered",
        "exclusion_reason": None,
        "source_paths": ["plugins/craft/capabilities/example.py"],
    }

    assert builder.merge_discovery({stale["function_id"]: stale}, []) == []


def test_web_scanner_merges_http_methods_with_rest_and_audits_dynamic_calls():
    builder = _builder_module()
    found = builder.scan_web_source(
        """fetch('/api/items');
fetch('/api/items', {method: 'POST'});
bridge.invoke('create_item');
fetch('file://local/test.json');
fetch(endpoint);""",
        "dist/web/example.js",
    )

    assert set(found) == {
        "rest:GET:/api/items",
        "rest:POST:/api/items",
        "bridge:invoke:create_item",
        "web_gap:dynamic_fetch:dist/web/example.js:5",
    }
    assert found["rest:GET:/api/items"]["current_consumers"] == {"Web"}
    assert found["rest:POST:/api/items"]["current_consumers"] == {"Web"}
    assert found["bridge:invoke:create_item"]["stability"] == "stable"
    assert found["web_gap:dynamic_fetch:dist/web/example.js:5"]["stability"] == "experimental"


def test_capability_scanner_uses_registered_descriptor_ids_not_permission_literals():
    builder = _builder_module()
    source = (
        'CapabilitySpec(id="craft.real.read", permissions=("craft.write",), '
        'subject_concepts=("craft.bop.version",))\n'
    )

    found = builder.capability_ids_in_source(source, {"craft.real.read"})

    assert found == {"craft.real.read"}


def test_discovery_preserves_experimental_stability_for_dynamic_web_gaps():
    builder = _builder_module()

    discovered = {row["function_id"]: row for row in builder.discover_user_functions()}

    assert discovered["web_gap:dynamic_fetch:dist/web/core/auth_state.js:55"]["stability"] == "experimental"


def test_agent_runtime_scanner_registers_static_and_parameterized_endpoints():
    builder = _builder_module()
    found = builder.scan_agent_runtime_routes(REPOSITORY_ROOT)

    assert {
        "agent_runtime:GET:/v1/tools",
        "agent_runtime:GET:/v1/sessions",
        "agent_runtime:POST:/v1/sessions",
        "agent_runtime:GET:/v1/sessions/{session_gid}",
        "agent_runtime:DELETE:/v1/sessions/{session_gid}",
        "agent_runtime:POST:/v1/runs",
        "agent_runtime:GET:/v1/runs/{session_gid}",
        "agent_runtime:GET:/v1/runs/{session_gid}/approvals",
        "agent_runtime:POST:/v1/runs/{session_gid}/messages",
        "agent_runtime:POST:/v1/runs/{session_gid}/messages/stream",
        "agent_runtime:POST:/v1/runs/{session_gid}/approvals/{parameter_2}/decision",
    } <= set(found)
    assert all(row["domain"] == "Agent" for row in found.values())


def test_check_cli_passes_when_source_evidence_matches_with_governance_candidates():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "User Function Registry check passed" in result.stdout


def test_strict_cli_returns_nonzero_when_baseline_contains_unreviewed_stable_candidates():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--strict"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing reviewed disposition" in result.stderr


def test_review_linkage_rejects_registry_row_missing_from_domain_review():
    builder = _builder_module()
    row = {
        "function_id": "rest:GET:/api/example",
        "domain": "Base Platform",
        "stability": "stable",
        "source_paths": ["backend/routers/example.py"],
    }

    errors = builder.review_disposition_errors(
        {row["function_id"]: row}, [], {}
    )

    assert errors == ["missing reviewed disposition: rest:GET:/api/example"]


def test_review_linkage_rejects_target_owned_by_another_domain():
    builder = _builder_module()
    row = {
        "function_id": "rest:GET:/api/projects",
        "domain": "Project Management",
        "stability": "stable",
        "source_paths": ["backend/routers/projects.py"],
    }
    review = {
        "domain": "Project Management",
        "unreviewed_functions": {},
        "excluded_functions": {},
        "capabilities": {
            "craft.project.search": {
                "kind": "existing",
                "function_dispositions": {
                    row["function_id"]: {
                        "resolution": "existing_capability",
                        "source_paths": row["source_paths"],
                    }
                },
            }
        },
    }

    errors = builder.review_disposition_errors(
        {row["function_id"]: row}, [review], {"craft.project.search": "craft"}
    )

    assert errors == ["capability owner mismatch: rest:GET:/api/projects"]


def test_registry_projection_ignores_stale_review_source_evidence():
    builder = _builder_module()
    function_id = "rest:GET:/api/projects"
    row = {
        "function_id": function_id,
        "domain": "Project Management",
        "stability": "stable",
        "source_paths": ["backend/routers/projects_v2.py"],
        "target_capability": None,
        "classification": "unreviewed",
        "migration_status": "candidate",
        "exclusion_reason": None,
    }
    review = {
        "domain": "Project Management",
        "excluded_functions": {},
        "capabilities": {
            "base.project.search": {
                "kind": "existing",
                "function_dispositions": {
                    function_id: {
                        "resolution": "existing_capability",
                        "source_paths": ["backend/routers/projects.py"],
                    }
                },
            }
        },
    }

    projected = builder.apply_review_dispositions(
        {function_id: row}, [review], {"base.project.search": "project_management"}
    )

    assert projected[function_id]["target_capability"] is None
    assert projected[function_id]["classification"] == "unreviewed"
