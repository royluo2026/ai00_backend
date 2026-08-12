"""Governed ontology concept reads and non-persistent mapping assessment."""
from __future__ import annotations

from typing import Any

from plugins.ontology.ontology_backend.concepts import concept_summary, project_concept, resolve_term
from plugins.ontology.ontology_backend.mappings import assess_objects
from plugins.ontology.ontology_backend.repository import OntologyReleaseRepository
from backend.domain_ports.ontology import ConceptRef, OntologyVersionRef

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef


ONTOLOGY_VERSION_REF_SCHEMA = {
    "type": "object",
    "required": ["release_gid", "content_hash", "revision_ref"],
    "properties": {
        "release_gid": {"type": "string"},
        "content_hash": {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
        "revision_ref": {"anyOf": [{
            "type": "object",
            "required": ["repository", "commit_id", "content_hash"],
            "properties": {
                "repository": {
                    "type": "object",
                    "required": ["tenant_id", "repository_id", "owner_domain", "resource_id"],
                    "properties": {name: {"type": "string"} for name in ("tenant_id", "repository_id", "owner_domain", "resource_id")},
                    "additionalProperties": False,
                },
                "commit_id": {"type": "string", "pattern": "^cmt_[0-9a-f]{40}$"},
                "content_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            },
            "additionalProperties": False,
        }, {"type": "null"}]},
    },
}

CONCEPT_RESULT_SCHEMA = {
    "type": "object",
    "required": ["concept", "view", "release_gid", "release_sha256", "ontology_version_ref"],
    "properties": {
        "concept": {},
        "view": {"type": "string", "enum": ["summary", "schema"]},
        "release_gid": {"type": "string"},
        "release_sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        "ontology_version_ref": ONTOLOGY_VERSION_REF_SCHEMA,
    },
}

RESOLUTION_RESULT_SCHEMA = {
    "type": "object",
    "required": [
        "status", "matched_by", "concept", "candidates", "release_gid",
        "release_sha256", "ontology_version_ref",
    ],
    "properties": {
        "status": {"type": "string", "enum": ["resolved", "ambiguous", "candidates", "unresolved"]},
        "matched_by": {},
        "concept": {},
        "candidates": {"type": "array", "items": {}},
        "release_gid": {"type": "string"},
        "release_sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        "ontology_version_ref": ONTOLOGY_VERSION_REF_SCHEMA,
    },
}

MAPPING_ASSESSMENT_SCHEMA = {
    "type": "object",
    "required": ["conclusion", "reasons", "checks"],
    "properties": {
        "conclusion": {
            "type": "string",
            "enum": ["compatible", "incompatible", "expert_review_required"],
        },
        "reasons": {"type": "array", "items": {"type": "string"}},
        "checks": {},
    },
}


def _release_evidence(release: dict[str, Any]) -> EvidenceRef:
    digest = str(release["content_sha256"])
    return EvidenceRef(
        kind="ontology.release",
        reference=f"ois://{release.get('ois_object_key') or 'ontology/releases/' + str(release['release_gid'])}",
        digest=f"sha256:{digest}",
        summary=f"Immutable ontology release {release['release_gid']}",
        metadata={"release_gid": release["release_gid"]},
    )


def _version_ref(release: dict[str, Any]) -> OntologyVersionRef:
    return OntologyVersionRef(
        release_gid=str(release["release_gid"]),
        content_hash=f"sha256:{str(release['content_sha256']).removeprefix('sha256:')}",
    )


def _project_with_ref(item: dict[str, Any], view: str, version: OntologyVersionRef) -> dict[str, Any]:
    projected = project_concept(item, view)
    projected["concept_ref"] = ConceptRef(
        concept_id=str(item["stable_gid"]),
        kind=str(item["kind"]),
        ontology_version=version,
    ).model_dump(mode="json")
    return projected


def resolve_concept(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    repository = OntologyReleaseRepository()
    release = repository.resolve_release(str(payload.get("release_gid") or "").strip() or None)
    version = _version_ref(release)
    objects = repository.list_objects(release["release_gid"], kinds={"concept", "property", "relation", "mapping", "constraint"})
    resolved = resolve_term(str(payload.get("term") or ""), objects)
    candidates = [_project_with_ref(item, "summary", version) for item in resolved.pop("candidates", [])]
    concept = resolved.get("concept")
    if concept is not None:
        resolved["concept"] = _project_with_ref(concept, "summary", version)
    data = {
        **resolved,
        "candidates": candidates,
        "release_gid": release["release_gid"],
        "release_sha256": release["content_sha256"],
        "ontology_version_ref": version.model_dump(mode="json"),
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
    version = _version_ref(release)
    item = repository.get_object(release["release_gid"], kind, stable_gid)
    if not item:
        raise LookupError("ontology object not found in the resolved release")
    return CapabilityOutput(
        data={
            "concept": _project_with_ref(item, view, version), "view": view,
            "release_gid": release["release_gid"], "release_sha256": release["content_sha256"],
            "ontology_version_ref": version.model_dump(mode="json"),
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
        "owner": "ontology", "plugin_callable": True, "permissions": (),
        "subject_concepts": ("ontology.release", "ontology.object"),
        "tags": ("ontology", "read"),
    }
    registry.register(CapabilitySpec(
        **common, id="ontology.concept.resolve", description="Resolve a term without guessing across an immutable release.",
        use_when="A caller has a human term or external identity.", do_not_use_when="The stable object identity is already known.",
        effects=("read:ontology.object",), output_schema=RESOLUTION_RESULT_SCHEMA,
        input_schema={"type": "object", "required": ["term"], "properties": {"term": {"type": "string"}, "release_gid": {"type": "string"}}}), resolve_concept)
    registry.register(CapabilitySpec(
        **common, id="ontology.concept.get", description="Read a summary or schema view pinned to an immutable release.",
        use_when="A stable ontology identity is known.", do_not_use_when="The caller only has an ambiguous term.",
        effects=("read:ontology.object",), output_schema=CONCEPT_RESULT_SCHEMA,
        input_schema={"type": "object", "required": ["stable_gid"], "properties": {"stable_gid": {"type": "string"}, "kind": object_ref["properties"]["kind"], "release_gid": {"type": "string"}, "view": {"type": "string", "enum": ["summary", "schema"]}}}), get_concept)
    registry.register(CapabilitySpec(
        **common, id="ontology.mapping.assess", description="Assess deterministic mapping compatibility without persisting a mapping.",
        use_when="Two typed ontology objects may correspond.", do_not_use_when="Only names are available and an automatic decision is expected.",
        effects=("assess:ontology.mapping",), output_schema=MAPPING_ASSESSMENT_SCHEMA,
        input_schema={"type": "object", "required": ["source", "target"], "properties": {"source": object_ref, "target": object_ref, "existing_mappings": {"type": "array", "items": {"type": "object"}}}}), assess_mapping)
