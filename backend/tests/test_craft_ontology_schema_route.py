from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from plugins.craft.craft_backend.routers import ontology


def test_bop_schema_route_reads_nested_concept_and_pins_release(monkeypatch):
    calls = []

    async def invoke(capability_id, payload, _user, _principal, **_kwargs):
        calls.append((capability_id, payload))
        if capability_id == "ontology.concept.resolve":
            return {
                "status": "resolved", "matched_by": "node_type_binding",
                "concept": {"stable_gid": "concept.operation"},
                "release_gid": "release-1",
            }
        return {"concept": {"stable_gid": "concept.operation", "properties": []}}

    monkeypatch.setattr(ontology, "_invoke", invoke)

    result = asyncio.run(ontology.get_class_schema("operation", {}, object()))

    assert result["concept"]["stable_gid"] == "concept.operation"
    assert calls == [
        ("ontology.concept.resolve", {"term": "operation"}),
        ("ontology.concept.get", {
            "stable_gid": "concept.operation", "kind": "concept",
            "view": "schema", "release_gid": "release-1",
        }),
    ]


@pytest.mark.parametrize(("capability_id", "version"), [
    ("ontology.concept.get", 2),
    ("ontology.concept.resolve", 2),
    ("ontology.release.get", 1),
    ("ontology.schema.change.apply", 1),
])
def test_compatibility_gateway_pins_only_changed_reads_to_v2(monkeypatch, capability_id, version):
    calls = []

    async def invoke(_gateway, envelope):
        calls.append(envelope)
        return SimpleNamespace(ok=True, data={"release_gid": "release-1"})

    monkeypatch.setattr(ontology, "get_default_gateway", lambda: SimpleNamespace(catalog_release="release-test"))
    monkeypatch.setattr(ontology, "invoke_trusted_web_compatibility", invoke)
    principal = SimpleNamespace(model_dump=lambda: {
        "user_id": "user-1", "authentication_method": "test",
        "authenticated_at": "2026-09-07T00:00:00Z",
    })
    result = asyncio.run(ontology._invoke(capability_id, {}, {"team_id": "team-1"}, principal))
    assert result == {"release_gid": "release-1"}
    assert calls[0].major_version == version
    assert calls[0].catalog_release == "release-test"
