from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import validate

from plugins.factory.factory_backend.domain.models import PhysicalStructure


ROOT = Path(__file__).resolve().parents[3]


def test_factory_has_one_official_provider():
    document = json.loads(
        (ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8")
    )
    factory = next(item for item in document["domains"] if item["domain_id"] == "factory")

    assert factory["artifact"]["module"] == "factory_backend.capabilities"
    assert factory["database"]["database_name"] == "ai00_factory"


def test_factory_model_excludes_bop_plan_nodes():
    assert "line_process" not in PhysicalStructure.model_fields
    assert "station_process" not in PhysicalStructure.model_fields


def test_factory_repository_decodes_json_columns_for_provider_consumers():
    from plugins.factory.factory_backend.infrastructure.repository import _decode_json_fields

    row = _decode_json_fields(
        {
            "gid": "factory-1",
            "attributes": '{"team_id":"team-1"}',
            "specification": '{"stations":[]}',
            "meta": '{"source":"e2e"}',
        }
    )

    assert row["attributes"] == {"team_id": "team-1"}
    assert row["specification"] == {"stations": []}
    assert row["meta"] == {"source": "e2e"}


def test_factory_compatibility_uses_user_tenant_when_team_is_missing():
    from plugins.factory.factory_backend.api.compatibility import (
        build_web_compatibility_envelope,
    )

    envelope = build_web_compatibility_envelope(
        SimpleNamespace(catalog_release="rel-test"),
        capability_id="factory.structure.search",
        payload={"kind": "factory"},
        current_user={
            "gid": "user-1",
            "team_id": None,
            "org_role": "member",
            "system_role": "member",
        },
        principal=SimpleNamespace(
            model_dump=lambda: {
                "user_id": "user-1",
                "authentication_method": "jwt",
                "authenticated_at": "2026-08-14T00:00:00Z",
            }
        ),
        request_id="request-1",
        trace_id="trace-1",
    )

    assert envelope.identity.tenant.tenant_id == "user:user-1"


def test_factory_provider_registers_only_factory_owned_stable_descriptors():
    from plugins.factory.factory_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)

    assert registry.items
    assert {descriptor.owner_domain for _, _, descriptor in registry.items} == {"factory"}
    assert all(descriptor.lifecycle_status == "stable" for _, _, descriptor in registry.items)
    assert all(spec.confirmation == ("none" if spec.risk.value == "read" else "user") for spec, _, _ in registry.items)


def test_factory_writes_use_domain_transactions_without_platform_enlistment():
    from plugins.factory.factory_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)

    for spec, _, descriptor in registry.items:
        expected = "strong" if spec.risk.value == "read" else "external"
        assert descriptor.consistency_policy == expected, spec.id


@pytest.mark.parametrize(
    ("capability_id", "payload"),
    [
        ("factory.structure.search", {"kind": "factory", "limit": 200}),
        (
            "factory.structure.create",
            {"kind": "factory", "name": "Assembly", "attributes": {"team_id": "team-1"}},
        ),
        (
            "factory.resource_catalog.search",
            {"resource_type": "fixture", "status": "published", "limit": 20},
        ),
        (
            "factory.asset.register",
            {"asset_no": "EQ-1", "asset_type": "equipment", "meta": {}},
        ),
    ],
)
def test_factory_descriptor_accepts_supported_provider_payloads(capability_id, payload):
    from plugins.factory.factory_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)
    descriptor = next(
        descriptor
        for spec, _, descriptor in registry.items
        if spec.id == capability_id
    )

    validate(instance=payload, schema=descriptor.input_schema)


@pytest.mark.parametrize(
    ("capability_id", "data"),
    [
        ("factory.structure.search", []),
        ("factory.structure.create", {"gid": "factory-1", "version": 1}),
    ],
)
def test_factory_descriptor_accepts_supported_provider_outputs(capability_id, data):
    from plugins.factory.factory_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)
    descriptor = next(
        descriptor
        for spec, _, descriptor in registry.items
        if spec.id == capability_id
    )

    validate(instance={"data": data}, schema=descriptor.output_schema)
