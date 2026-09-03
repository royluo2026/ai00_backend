from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.knowledge.knowledge_backend.capabilities.resource_model_mapping import (
    ResourceModelMappingProvider,
    normalize_code,
    register_resource_model_mapping_capability,
)


MODEL_T01 = {
    "model_id": "tool-t01",
    "version_id": "v3",
    "snapshot_hash": "sha256:" + "1" * 64,
    "artifact_ref": {
        "artifact_id": "artifact-t01",
        "media_type": "application/octet-stream",
        "sha256": "2" * 64,
        "byte_size": 42,
        "version": 1,
    },
}


class StubRepository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def resolve(self, keys, *, tenant_gid, as_of=None):
        self.calls.append((keys, tenant_gid, as_of))
        wanted = set(keys)
        return [
            row for row in self.rows
            if (row["resource_type"], row["normalized_code"]) in wanted
        ]


def row(resource_type, normalized_code, model_ref, mapping_version=1):
    return {
        "resource_type": resource_type,
        "normalized_code": normalized_code,
        "model_ref_json": json.dumps(model_ref),
        "mapping_version": mapping_version,
        "content_hash": "sha256:" + "3" * 64,
    }


@pytest.fixture
def context():
    return CapabilityContext(user_gid="user-1", team_gid="team-1")


def test_resolve_returns_typed_version_pinned_models(context):
    repository = StubRepository([row("tool", "t-01", MODEL_T01)])
    provider = ResourceModelMappingProvider(repository)

    result = provider.resolve(
        {"items": [{"resource_type": "tool", "code": "  Ｔ-０１  "}]},
        context,
    )

    assert result.data["resolved"] == [{
        "resource_type": "tool",
        "code": "  Ｔ-０１  ",
        "normalized_code": "t-01",
        "model_ref": MODEL_T01,
    }]
    assert result.data["unresolved"] == []
    assert result.data["ambiguous"] == []
    assert result.data["mapping_snapshot_hash"].startswith("sha256:")
    assert repository.calls == [((("tool", "t-01"),), "team-1", None)]


def test_resolve_reports_ambiguity_without_picking_a_model(context):
    second = {**MODEL_T01, "model_id": "fixture-f01", "version_id": "v4"}
    repository = StubRepository([
        row("fixture", "f-01", MODEL_T01, 1),
        row("fixture", "f-01", second, 2),
    ])

    result = ResourceModelMappingProvider(repository).resolve(
        {"items": [{"resource_type": "fixture", "code": "F-01"}]},
        context,
    )

    assert result.data["resolved"] == []
    assert result.data["ambiguous"] == [{
        "resource_type": "fixture",
        "code": "F-01",
        "normalized_code": "f-01",
        "candidates": [MODEL_T01, second],
    }]


def test_resolve_reports_unresolved_and_rejects_invalid_or_oversized_input(context):
    provider = ResourceModelMappingProvider(StubRepository([]))
    result = provider.resolve(
        {"items": [{"resource_type": "equipment", "code": "E-404"}]}, context
    )
    assert result.data["unresolved"][0]["code"] == "E-404"

    with pytest.raises(CapabilityBusinessError, match="resource_type_invalid"):
        provider.resolve({"items": [{"resource_type": "person", "code": "P-1"}]}, context)

    with pytest.raises(CapabilityBusinessError, match="mapping_batch_limit_exceeded"):
        provider.resolve({
            "items": [
                {"resource_type": "tool", "code": f"T-{index}"}
                for index in range(501)
            ]
        }, context)


def test_contract_is_closed_and_registered_as_a_knowledge_read():
    class Registry:
        def register(self, spec, handler, *, descriptor):
            self.spec = spec
            self.handler = handler
            self.descriptor = descriptor

    registry = Registry()
    register_resource_model_mapping_capability(registry, StubRepository([]))

    assert registry.spec.id == "knowledge.resource_model_mapping.resolve"
    assert registry.spec.version == 1
    assert registry.spec.owner == "knowledge"
    assert registry.spec.risk.value == "read"
    assert registry.spec.input_schema["additionalProperties"] is False
    assert registry.spec.output_schema["additionalProperties"] is False
    assert registry.descriptor.evidence_policy == "required"
    assert registry.descriptor.consistency_policy == "strong"


def test_normalize_code_rejects_blank_values():
    assert normalize_code("Ｔ-０１") == "t-01"
    with pytest.raises(CapabilityBusinessError, match="resource_code_invalid"):
        normalize_code("　")


def test_mapping_storage_uses_the_current_knowledge_table_prefix():
    root = Path(__file__).resolve().parents[2]
    source = (root / "plugins/knowledge/knowledge_backend/capabilities/resource_model_mapping.py").read_text(encoding="utf-8")
    migration = (root / "backend/db/migrations/domains/knowledge/0004_resource_model_mappings.sql").read_text(encoding="utf-8")

    assert "workmanship_knowledge_resource_model_mappings" in source
    assert "workmanship_knowledge_resource_model_mappings" in migration
    assert "workmanship_craft_" not in source
    assert "workmanship_bop_" not in source


def test_resolve_requires_tenant_scope_and_rejects_invalid_stored_model_refs():
    provider = ResourceModelMappingProvider(StubRepository([]))
    with pytest.raises(CapabilityBusinessError) as missing_tenant:
        provider.resolve(
            {"items": [{"resource_type": "tool", "code": "T-01"}]},
            CapabilityContext(user_gid="user-1"),
        )
    assert missing_tenant.value.code == "tenant_context_required"

    invalid = {**MODEL_T01, "snapshot_hash": "latest"}
    provider = ResourceModelMappingProvider(StubRepository([row("tool", "t-01", invalid)]))
    with pytest.raises(CapabilityBusinessError) as invalid_mapping:
        provider.resolve(
            {"items": [{"resource_type": "tool", "code": "T-01"}]}, context=CapabilityContext(user_gid="user-1", team_gid="team-1")
        )
    assert invalid_mapping.value.code == "mapping_data_invalid"
