from __future__ import annotations

import json
from pathlib import Path

from backend.capabilities.models_next import CapabilitySpec
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.catalog import CatalogRelease
from backend.capability_v2.docs.generator import (
    DOMAIN_DOC_PATHS, build_documentation, example_for_schema, generated_files,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec as adapt_v1_spec


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "docs/governance/capability-catalog-release.json"
DOCS_ROOT = ROOT / "docs/capabilities"


def _catalog() -> CatalogRelease:
    return CatalogRelease.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))


def test_v1_adapter_makes_required_fields_possible_under_closed_schema():
    descriptor = adapt_v1_spec(CapabilitySpec(
        id="craft.example.get", owner="craft",
        input_schema={"type": "object", "required": ["version_gid"]},
    ))
    assert "version_gid" in descriptor.input_schema["properties"]
    validate_payload(dict(descriptor.input_schema), {"version_gid": "example"})


def test_v1_adapter_preserves_explicit_typed_any_json_schema():
    any_json = {"type": ["object", "array", "string", "number", "boolean", "null"]}
    descriptor = adapt_v1_spec(CapabilitySpec(
        id="base.json.put",
        owner="base",
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": any_json},
        },
    ))

    assert descriptor.input_schema["properties"]["value"] == any_json
    validate_payload(dict(descriptor.input_schema), {"value": [1, {"nested": True}]})
    validate_payload(dict(descriptor.input_schema), {"value": {"items": [1, 2]}})


def test_minimal_example_satisfies_sha256_string_patterns():
    """Breaks if generated machine examples use a generic string for a digest field."""
    schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}

    example = example_for_schema(schema)

    assert example == "sha256:" + "0" * 64
    validate_payload(schema, example)


def test_deprecated_empty_operation_enum_is_compatibility_unconstrained():
    validate_payload({"type": "string", "enum": []}, "legacy-operation")


def test_every_descriptor_has_generated_page_and_valid_minimal_example():
    catalog = _catalog()
    files = generated_files(catalog)
    for descriptor in catalog.descriptors:
        page = f"{DOMAIN_DOC_PATHS[descriptor.owner_domain]}/{descriptor.id}@{descriptor.major_version}.md"
        assert page in files
        example = example_for_schema(descriptor.input_schema)
        validate_payload(dict(descriptor.input_schema), example)
        assert descriptor.id in files[page]
        assert "插件" in files[page] and "Agent" in files[page]


def test_machine_catalog_contains_release_bound_agent_mcp_and_openapi_views():
    document = build_documentation(_catalog())
    machine = document.machine_catalog
    assert machine["release_id"] == _catalog().release_id
    assert machine["catalog_hash"] == _catalog().catalog_hash
    assert len(machine["capabilities"]) == len(_catalog().descriptors)
    assert all(item["catalog_release"] == machine["release_id"] for item in machine["capabilities"])
    assert all("schema_precision" in item and "exposure_blockers" in item for item in machine["capabilities"])
    assert all("execution_budget" in item for item in machine["capabilities"])
    assert all(item["exposure"]["agent"] for item in machine["agent_tools"])
    assert all(item["exposure"]["mcp"] for item in machine["mcp_tools"])
    assert machine["openapi_fragment"]["openapi"] == "3.1.0"
    api_operation = next(iter(machine["openapi_fragment"]["paths"].values()))["post"]
    response_schema = api_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert "operation_ref" in response_schema["properties"]
    assert {item["owner_domain"] for item in machine["capabilities"]} <= {
        "base", "agent", "craft", "digital_model", "factory", "project_management",
        "simulation", "ontology", "knowledge", "integration", "device",
    }


def test_capability_page_documents_every_execution_budget_field():
    catalog = _catalog()
    descriptor = catalog.descriptors[0]
    page = generated_files(catalog)[
        f"{DOMAIN_DOC_PATHS[descriptor.owner_domain]}/{descriptor.id}@{descriptor.major_version}.md"
    ]

    for label in (
        "memory_class", "max_input_bytes", "max_output_bytes", "collection_policy",
        "max_page_size", "max_parallel_per_consumer", "max_parallel_per_tenant",
        "overload_policy",
    ):
        assert label in page


def test_checked_in_manual_has_no_generation_drift():
    expected = generated_files(_catalog())
    actual = {
        path.relative_to(DOCS_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in DOCS_ROOT.rglob("*") if path.is_file()
    }
    assert actual == expected


def test_plugin_sdk_declares_full_v2_result_contract():
    source = (ROOT / "packages/plugin-sdk/src/index.ts").read_text(encoding="utf-8")
    for field in ("operation_ref", "artifact_refs", "evidence", "correlation"):
        assert field in source
    assert '"outcome_unknown"' in source
