from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from .ontology_proposals_next import create_proposal


IDS = ("ontology.schema.change.apply", "ontology.mapping.change.apply")


def register_reviewed_capabilities(registry):
    for capability_id in IDS:
        spec = CapabilitySpec(
            id=capability_id, owner="ontology", description="Convert a requested schema or mapping change into a governed Ontology proposal.",
            use_when="A consumer needs to propose an Ontology change.", do_not_use_when="The caller expects direct mutable schema CRUD.",
            risk=CapabilityRisk.WRITE, confirmation="user", permissions=("ontology.propose",), plugin_callable=True,
            input_schema={"type": "object", "required": ["base_release_gid", "changes"], "properties": {"base_release_gid": {"type": "string"}, "changes": {"type": "array", "items": {"type": "object"}}}, "additionalProperties": False},
            output_schema={"type": "object", "required": ["data"], "properties": {"data": {}}}, tags=("ontology", "proposal"),
        )
        registry.register(spec, create_proposal)

