from __future__ import annotations

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.business_definition import (
    business_definition_hash, substantive_business_definition_errors,
)
from backend.capability_v2.catalog import complete_governance_metadata
from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.ontology.ontology_backend.capabilities import ontology_concepts_next as reads
from plugins.ontology.ontology_backend.provider import GovernedRegistry


LEGACY_HASHES = {
    "ontology.concept.get": "sha256:5cfc784d580ec3982b2dc64ff2abcf781d778faac2bf9ad9b14a1778cadd6022",
    "ontology.concept.resolve": "sha256:a432321bfbbf05e0af862c9009858887842d07e4492194d2bab50c83a1053cc2",
    "ontology.object.list": "sha256:1b65d66533682ec2fac3c7ecc81e80f51e9df4d61de04ffc0ebb850751bd58b2",
}
CONTEXT = CapabilityContext(user_gid="actor", team_gid="team")


@pytest.fixture
def registry():
    result = CapabilityRegistry()
    reads.register_ontology_concept_capabilities(GovernedRegistry(result))
    return result


@pytest.fixture
def repository(monkeypatch):
    class Repository:
        objects = [
            {"kind": "concept", "stable_gid": "parent", "name": "Parent"},
            {"kind": "concept", "stable_gid": "child", "parent_gid": "parent", "name": "Child"},
            {"kind": "property", "stable_gid": "inherited", "class_gid": "parent", "name": "Inherited"},
            {"kind": "relation", "stable_gid": "own", "domain_class_gid": "child", "name": "Own"},
        ]

        def resolve_release(self, release_gid=None):
            assert release_gid == "release-1"
            return {"release_gid": "release-1", "content_sha256": "f" * 64}

        def get_object(self, release_gid, kind, stable_gid):
            assert release_gid == "release-1"
            return next((item for item in self.objects if item["kind"] == kind and item["stable_gid"] == stable_gid), None)

        def list_objects(self, release_gid, kinds=None):
            assert release_gid == "release-1"
            return [item for item in self.objects if item["kind"] in kinds]

        def list_objects_page(self, release_gid, *, kinds, limit, offset, query):
            items = self.list_objects(release_gid, kinds)
            return items[offset:offset + limit], len(items)

    instance = Repository()
    monkeypatch.setattr(reads, "OntologyReleaseRepository", lambda: instance)
    return instance


@pytest.mark.parametrize("capability_id", LEGACY_HASHES)
def test_v1_business_definition_is_immutable(registry, capability_id):
    descriptor = complete_governance_metadata(registry.get(capability_id, 1).descriptor)
    assert business_definition_hash(descriptor) == LEGACY_HASHES[capability_id]


@pytest.mark.parametrize("capability_id", LEGACY_HASHES)
def test_v2_declares_substantive_business_definition(registry, capability_id):
    descriptor = registry.get(capability_id, 2).descriptor
    assert substantive_business_definition_errors(descriptor) == ()
    assert descriptor.business_invariants
    assert business_definition_hash(descriptor) != LEGACY_HASHES[capability_id]


def test_v1_does_not_acquire_inherited_schema_members(registry, repository):
    result = registry.get("ontology.concept.get", 1).handler(
        {"stable_gid": "child", "view": "schema", "release_gid": "release-1"}, CONTEXT,
    )
    assert "properties" not in result.data["concept"]
    assert "relations" not in result.data["concept"]


def test_v2_schema_inherits_members_from_the_same_immutable_release(registry, repository):
    registered = registry.get("ontology.concept.get", 2)
    result = registered.handler(
        {"stable_gid": "child", "view": "schema", "release_gid": "release-1"}, CONTEXT,
    )
    assert [item["stable_gid"] for item in result.data["concept"]["properties"]] == ["inherited"]
    assert [item["stable_gid"] for item in result.data["concept"]["relations"]] == ["own"]
    assert result.data["concept"]["concept_ref"]["ontology_version"] == {
        "release_gid": "release-1", "content_hash": "sha256:" + "f" * 64, "revision_ref": None,
    }
    validate_payload(registered.descriptor.output_schema, result.data)


def test_v2_resolution_keeps_ambiguity_and_bounds_candidates(registry, repository):
    repository.objects = [
        {"kind": "concept", "stable_gid": f"candidate-{index}", "name": "Same"}
        for index in range(25)
    ]
    registered = registry.get("ontology.concept.resolve", 2)
    result = registered.handler({"term": "Same", "release_gid": "release-1"}, CONTEXT)
    assert result.data["status"] == "ambiguous"
    assert result.data["concept"] is None
    assert len(result.data["candidates"]) == 20
    validate_payload(registered.descriptor.output_schema, result.data)
    legacy = registry.get("ontology.concept.resolve", 1).handler(
        {"term": "Same", "release_gid": "release-1"}, CONTEXT,
    )
    assert len(legacy.data["candidates"]) == 25


def test_v2_list_is_paged_and_release_pinned(registry, repository):
    registered = registry.get("ontology.object.list", 2)
    result = registered.handler(
        {"kinds": ["concept"], "limit": 1, "offset": 1, "release_gid": "release-1"}, CONTEXT,
    )
    assert result.data["total"] == 2
    assert [item["stable_gid"] for item in result.data["items"]] == ["child"]
    assert result.data["items"][0]["concept_ref"]["ontology_version"]["release_gid"] == "release-1"
    validate_payload(registered.descriptor.output_schema, result.data)
    with pytest.raises(ValueError):
        validate_payload(registered.descriptor.input_schema, {"limit": 101})
    with pytest.raises(ValueError):
        validate_payload(registered.descriptor.output_schema, {**result.data, "unpublished_field": True})


@pytest.mark.parametrize("mutation", [None, "effect", "schema", "version", "identity"])
def test_collection_grandfathering_requires_the_entire_immutable_definition(registry, mutation):
    from copy import deepcopy
    from backend.capability_v2.catalog import build_release
    from backend.scripts import build_capability_catalog as builder

    descriptor = complete_governance_metadata(registry.get("ontology.concept.resolve", 1).descriptor)
    if mutation == "effect":
        descriptor = descriptor.model_copy(update={"business_effect": "Changed business meaning."})
    elif mutation == "schema":
        schema = deepcopy(descriptor.output_schema)
        schema["properties"]["new_field"] = {"type": "string"}
        descriptor = descriptor.model_copy(update={"output_schema": schema})
    elif mutation == "version":
        descriptor = descriptor.model_copy(update={"major_version": 2})
    elif mutation == "identity":
        descriptor = descriptor.model_copy(update={"id": "ontology.concept.new"})
    baseline = {f"{key}@1": value for key, value in LEGACY_HASHES.items()}
    paths = builder.legacy_collection_paths([descriptor], baseline)
    if mutation is None:
        assert paths == {("ontology.concept.resolve", 1, "output_schema.candidates")}
        build_release([descriptor], grandfathered_unbounded_paths=paths, enforce_collection_boundaries=True)
    else:
        assert paths == set()
        with pytest.raises(ValueError, match="unbounded stable collection"):
            build_release([descriptor], grandfathered_unbounded_paths=paths, enforce_collection_boundaries=True)


@pytest.mark.parametrize("mutation", [None, "changed_v1", "changed_v2", "new_identity", "partial_schema"])
def test_current_release_cannot_grandfather_a_matching_untrusted_previous_catalog(
    registry, monkeypatch, tmp_path, mutation,
):
    import json
    from copy import deepcopy
    from backend.capability_v2.catalog import build_release
    from backend.scripts import build_capability_catalog as builder

    # Validate the real immutable baseline before substituting provider discovery.
    baseline = builder.load_legacy_baseline(
        builder.REPOSITORY_ROOT / "docs/governance/capability-business-governance-legacy-baseline.json",
        catalog_path=builder.DEFAULT_OUTPUT,
    )
    original = registry.get("ontology.concept.resolve", 1)
    descriptor = complete_governance_metadata(original.descriptor)
    if mutation in {"changed_v1", "changed_v2"}:
        descriptor = descriptor.model_copy(update={
            "business_effect": "Changed nonbaseline business meaning.",
            "major_version": 2 if mutation == "changed_v2" else 1,
        })
    elif mutation == "new_identity":
        descriptor = descriptor.model_copy(update={"id": "ontology.concept.new"})
    elif mutation == "partial_schema":
        schema = deepcopy(descriptor.input_schema)
        schema["properties"]["new_selector"] = {"type": "string"}
        descriptor = descriptor.model_copy(update={"input_schema": schema})

    provider_registry = CapabilityRegistry()
    provider_registry.register(original.spec.model_copy(update={
        "id": descriptor.id, "version": descriptor.major_version,
    }), original.handler, descriptor=descriptor)
    previous = tmp_path / "previous-catalog.json"
    previous.write_text(json.dumps(builder._release_document(build_release([descriptor]))), encoding="utf-8")
    monkeypatch.setattr(builder, "DEFAULT_OUTPUT", previous)
    monkeypatch.setattr(builder, "build_capability_registry", lambda *_args: provider_registry)
    monkeypatch.setattr(builder, "load_legacy_baseline", lambda *_args, **_kwargs: baseline)

    if mutation is None:
        release = builder.current_release()
        assert business_definition_hash(release.descriptors[0]) == LEGACY_HASHES["ontology.concept.resolve"]
    else:
        with pytest.raises(ValueError, match="unbounded stable collection"):
            builder.current_release()
