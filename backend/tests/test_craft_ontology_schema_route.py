from __future__ import annotations

import asyncio

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
