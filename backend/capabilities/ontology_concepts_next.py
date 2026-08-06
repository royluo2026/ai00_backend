"""Governed ontology concept reads and non-persistent mapping assessment."""
from __future__ import annotations

from typing import Any

from backend.ontology.concepts import concept_summary, project_concept, resolve_term
from backend.ontology.mappings import assess_objects
from backend.ontology.repository import OntologyReleaseRepository

from .models_next import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef


def _release_evidence(release: dict[str, Any]) -> EvidenceRef:
    digest = str(release["content_sha256"])
    return EvidenceRef(
        kind="ontology.release",
        reference=f"ois://{release.get('ois_object_key') or 'ontology/releases/' + str(release['release_gid'])}",
        digest=f"sha256:{digest}",
        summary=f"Immutable ontology release {release['release_gid']}",
        metadata={"release_gid": release["release_gid"]},
    )


def resolve_concept(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    repository = OntologyReleaseRepository()
    release = repository.resolve_release(str(payload.get("release_gid") or "").strip() or None)
    objects = repository.list_objects(release["release_gid"], kinds={"concept", "property", "relation", "mapping", "constraint"})
    resolved = resolve_term(str(payload.get("term") or ""), objects)
    candidates = [concept_summary(item) for item in resolved.pop("candidates", [])]
    concept = resolved.get("concept")
    if concept is not None:
        resolved["concept"] = concept_summary(concept)
    data = {
        **resolved,
        "candidates": candidates,
        "release_gid": release["release_gid"],
        "release_sha256": release["content_sha256"],
    }
    return CapabilityOutput(data=data, evidence=(_release_evidence(release),))


def get_concept(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    stable_gid = str(payload.get("stable_gid") or "").strip()
    kind = str(payload.get("kind") or "concept").strip()
    view = str(payload.get("view") or "summary").strip()
    if not stable_gid:
        raise ValueError("stable_gid is required")
    repository = OntologyReleaseRepository()
    release = repository.resolve_release(str(payload.get("release_gid") or "").strip() or None)
    item = repository.get_object(release["release_gid"], kind, stable_gid)
    if not item:
        raise LookupError("ontology object not found in the resolved release")
    return CapabilityOutput(
        data={
            "concept": project_concept(item, view), "view": view,
            "release_gid": release["release_gid"], "release_sha256": release["content_sha256"],
        },
        evidence=(_release_evidence(release),),
    )


def assess_mapping(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    source = payload.get("source")
    target = payload.get("target")
    if not isinstance(source, dict) or not isinstance(target, dict):
        raise ValueError("source and target objects are required")
    existing = payload.get("existing_mappings") or []
    if not isinstance(existing, list) or any(not isinstance(item, dict) for item in existing):
        raise ValueError("existing_mappings must be an object array")
    return CapabilityOutput(data=assess_objects(source, target, existing))


def register_ontology_concept_capabilities(registry: Any) -> None:
    object_ref = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["concept", "property", "relation", "mapping", "constraint"]},
            "stable_gid": {"type": "string"},
        },
    }
    common = {
        "owner": "ontology", "plugin_callable": False, "permissions": (),
        "subject_concepts": ("ontology.release", "ontology.object"),
        "output_schema": {"type": "object"},
        "tags": ("ontology", "read"),
    }
    registry.register(CapabilitySpec(
        **common, id="ontology.concept.resolve", description="Resolve a term without guessing across an immutable release.",
        use_when="A caller has a human term or external identity.", do_not_use_when="The stable object identity is already known.",
        effects=("read:ontology.object",), input_schema={"type": "object", "required": ["term"], "properties": {"term": {"type": "string"}, "release_gid": {"type": "string"}}}), resolve_concept)
    registry.register(CapabilitySpec(
        **common, id="ontology.concept.get", description="Read a summary or schema view pinned to an immutable release.",
        use_when="A stable ontology identity is known.", do_not_use_when="The caller only has an ambiguous term.",
        effects=("read:ontology.object",), input_schema={"type": "object", "required": ["stable_gid"], "properties": {"stable_gid": {"type": "string"}, "kind": object_ref["properties"]["kind"], "release_gid": {"type": "string"}, "view": {"type": "string", "enum": ["summary", "schema"]}}}), get_concept)
    registry.register(CapabilitySpec(
        **common, id="ontology.mapping.assess", description="Assess deterministic mapping compatibility without persisting a mapping.",
        use_when="Two typed ontology objects may correspond.", do_not_use_when="Only names are available and an automatic decision is expected.",
        effects=("assess:ontology.mapping",), input_schema={"type": "object", "required": ["source", "target"], "properties": {"source": object_ref, "target": object_ref, "existing_mappings": {"type": "array", "items": {"type": "object"}}}}), assess_mapping)
