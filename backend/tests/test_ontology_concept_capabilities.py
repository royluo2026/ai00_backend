from unittest.mock import patch

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.ontology_concepts_next import (
    assess_mapping,
    get_concept,
    register_ontology_concept_capabilities,
    resolve_concept,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec as adapt_v1_spec


CONTEXT = CapabilityContext(user_gid="u1", team_gid="t1")


class Repository:
    release = {"release_gid": "rel1", "content_sha256": "f" * 64}
    objects = [
        {"kind": "concept", "stable_gid": "c-station-a", "name": "工位", "aliases": ["Station"], "description": "装配位置"},
        {"kind": "concept", "stable_gid": "c-station-b", "name": "岗位", "aliases": ["工位"], "description": "人员岗位"},
        {"kind": "property", "stable_gid": "p-cycle", "name": "节拍", "value_type": "number", "cardinality": "0..1"},
    ]

    def resolve_release(self, release_gid=None):
        assert release_gid in (None, "rel1")
        return self.release

    def list_objects(self, release_gid, kinds=None):
        assert release_gid == "rel1"
        return [item for item in self.objects if not kinds or item["kind"] in kinds]

    def get_object(self, release_gid, kind, stable_gid):
        return next((item for item in self.objects if item["kind"] == kind and item["stable_gid"] == stable_gid), None)


def _repository():
    return patch("backend.capabilities.ontology_concepts_next.OntologyReleaseRepository", return_value=Repository())


def test_resolve_returns_ambiguity_instead_of_guessing():
    with _repository():
        result = resolve_concept({"term": "工位"}, CONTEXT)
    assert result.data["status"] == "ambiguous"
    assert len(result.data["candidates"]) == 2
    assert result.data["release_gid"] == "rel1"
    assert result.data["release_sha256"] == "f" * 64


def test_resolve_stable_gid_is_deterministic():
    with _repository():
        result = resolve_concept({"term": "c-station-a", "release_gid": "rel1"}, CONTEXT)
    assert result.data["status"] == "resolved"
    assert result.data["concept"]["stable_gid"] == "c-station-a"
    assert result.data["matched_by"] == "stable_gid"
    assert result.data["concept"]["concept_ref"] == {
        "concept_id": "c-station-a",
        "kind": "concept",
        "ontology_version": {
            "release_gid": "rel1",
            "content_hash": "sha256:" + "f" * 64,
            "revision_ref": None,
        },
    }


def test_get_schema_is_version_pinned_and_does_not_return_arbitrary_graph():
    with _repository():
        result = get_concept(
            {"stable_gid": "p-cycle", "kind": "property", "release_gid": "rel1", "view": "schema"},
            CONTEXT,
        )
    assert result.data["view"] == "schema"
    assert result.data["release_gid"] == "rel1"
    assert result.data["concept"]["value_type"] == "number"
    assert result.data["ontology_version_ref"]["release_gid"] == "rel1"


def test_mapping_assess_never_claims_semantic_truth_from_names_only():
    result = assess_mapping(
        {"source": {"name": "工位"}, "target": {"name": "Station"}},
        CONTEXT,
    )
    assert result.data["conclusion"] == "expert_review_required"
    assert "stable" in " ".join(result.data["reasons"]).lower()


def test_mapping_assess_rejects_deterministic_kind_mismatch():
    result = assess_mapping(
        {
            "source": {"kind": "property", "stable_gid": "p1", "value_type": "number"},
            "target": {"kind": "concept", "stable_gid": "c1"},
        },
        CONTEXT,
    )
    assert result.data["conclusion"] == "incompatible"


def test_mapping_assess_rejects_existing_target_conflict():
    result = assess_mapping(
        {
            "source": {"kind": "property", "stable_gid": "p1", "value_type": "number"},
            "target": {"kind": "property", "stable_gid": "p2", "value_type": "number"},
            "existing_mappings": [
                {"source_stable_gid": "p1", "target_stable_gid": "p3"},
            ],
        },
        CONTEXT,
    )
    assert result.data["conclusion"] == "incompatible"
    assert result.data["checks"]["existing_mapping_unique"] is False

def test_registered_schemas_expose_no_arbitrary_query_language():
    registry = CapabilityRegistry()
    register_ontology_concept_capabilities(registry)
    assert registry.get("ontology.concept.get").spec.input_schema["properties"]["view"]["enum"] == ["summary", "schema"]
    for spec in registry.list():
        schema_text = str(spec.input_schema).lower()
        assert "sparql" not in schema_text
        assert "graphql" not in schema_text
        assert "raw_table" not in schema_text
        assert "path" not in spec.input_schema.get("properties", {})


def test_plugin_and_agent_contracts_declare_stable_ontology_refs():
    registry = CapabilityRegistry()
    register_ontology_concept_capabilities(registry)

    for capability_id in ("ontology.concept.resolve", "ontology.concept.get"):
        descriptor = adapt_v1_spec(registry.get(capability_id).spec)
        assert descriptor.exposure.plugin is True
        assert descriptor.exposure.agent is True
        assert "ontology_version_ref" in descriptor.output_schema["properties"]
        assert descriptor.output_schema["properties"]
