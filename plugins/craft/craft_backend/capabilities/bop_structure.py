"""Capability adapters for deterministic BOP execution structures."""
from __future__ import annotations

from typing import Any, Mapping

from backend.capabilities.models_next import (
    CapabilityContext,
    CapabilityOutput,
    CapabilitySpec,
    EvidenceRef,
)

from ..services.execution_structure import (
    build_execution_structure,
    linked_parts,
    project_work_package,
    repository,
)


def _required_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _expected_revision(payload: Mapping[str, Any]) -> int:
    value = payload.get("expected_revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected_revision must be an integer >= 1")
    return value


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unsupported fields: {', '.join(unknown)}")


def _structure_evidence(structure: Mapping[str, Any]) -> EvidenceRef:
    source = structure["source"]
    version_gid = str(source["bop_version_gid"])
    revision = source["revision"]
    return EvidenceRef(
        kind="craft.bop.execution_structure",
        reference=f"craft://bop/version/{version_gid}/execution-structure/r{revision}",
        digest=str(structure["content_hash"]),
        summary=f"BOP execution structure {version_gid} revision {revision}",
        metadata={"version_gid": version_gid, "revision": revision},
    )


def get_execution_structure(
    payload: dict[str, Any],
    _context: CapabilityContext,
) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid"})
    version_gid = _required_text(payload, "version_gid")
    structure = build_execution_structure(
        version_gid,
        expected_revision=None,
        preview=False,
    )
    return CapabilityOutput(data=structure, evidence=(_structure_evidence(structure),))


def preview_execution_structure(
    payload: dict[str, Any],
    _context: CapabilityContext,
) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid", "expected_revision"})
    version_gid = _required_text(payload, "version_gid")
    revision = _expected_revision(payload)
    structure = build_execution_structure(
        version_gid,
        expected_revision=revision,
        preview=True,
    )
    return CapabilityOutput(data=structure, evidence=(_structure_evidence(structure),))


def get_linked_parts(
    payload: dict[str, Any],
    _context: CapabilityContext,
) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid"})
    version_gid = _required_text(payload, "version_gid")
    aggregate = repository.load_bop_aggregate(version_gid, expected_revision=None)
    revision = aggregate.version["revision"]
    items = linked_parts(aggregate)
    evidence = EvidenceRef(
        kind="craft.bop.linked_parts",
        reference=f"craft://bop/version/{version_gid}/linked-parts/r{revision}",
        summary=f"Linked PBOM parts for BOP {version_gid}",
        metadata={"version_gid": version_gid, "revision": revision},
    )
    return CapabilityOutput(
        data={"version_gid": version_gid, "revision": revision, "items": items},
        evidence=(evidence,),
    )


def get_work_package(
    payload: dict[str, Any],
    _context: CapabilityContext,
) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid", "scope"})
    version_gid = _required_text(payload, "version_gid")
    scope = payload.get("scope")
    if not isinstance(scope, Mapping):
        raise ValueError("scope must be an object")
    if set(scope) - {"kind", "gid"}:
        raise ValueError("scope contains unsupported fields")
    kind = scope.get("kind")
    if kind not in {"line", "station", "role"}:
        raise ValueError("scope.kind must be line, station or role")
    scope_gid = _required_text(scope, "gid")
    aggregate = repository.load_bop_aggregate(version_gid, expected_revision=None)
    data = project_work_package(
        aggregate,
        scope_kind=str(kind),
        scope_gid=scope_gid,
    )
    evidence = EvidenceRef(
        kind="craft.bop.work_package",
        reference=(
            f"craft://bop/version/{version_gid}/work-package/"
            f"{kind}/{scope_gid}/r{data['revision']}"
        ),
        summary=f"BOP work package for {kind} {scope_gid}",
        metadata={
            "version_gid": version_gid,
            "revision": data["revision"],
            "scope_kind": kind,
            "scope_gid": scope_gid,
        },
    )
    return CapabilityOutput(data=data, evidence=(evidence,))


_STRUCTURE_OUTPUT = {
    "type": "object",
    "required": [
        "contract_id",
        "contract_version",
        "official",
        "source",
        "nodes",
        "operations",
        "dependencies",
        "conditions",
        "content_hash",
    ],
}


def register_bop_structure_capabilities(registry: Any) -> None:
    common = {
        "owner": "craft",
        "plugin_callable": True,
        "permissions": (),
    }
    registry.register(
        CapabilitySpec(
            id="craft.bop.execution_structure.get",
            description="Read the deterministic official execution structure of a published BOP.",
            use_when="A downstream system needs the official published execution source.",
            do_not_use_when="The BOP is a draft or the caller is editing it.",
            subject_concepts=("craft.bop.version", "craft.execution_structure"),
            effects=("read:craft.bop.execution_structure",),
            tags=("craft", "bop", "execution_structure", "read"),
            input_schema={
                "type": "object",
                "required": ["version_gid"],
                "properties": {"version_gid": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema=_STRUCTURE_OUTPUT,
            **common,
        ),
        get_execution_structure,
    )
    registry.register(
        CapabilitySpec(
            id="craft.bop.execution_structure.preview",
            description="Preview a draft BOP execution structure at an exact revision.",
            use_when="The caller needs a non-official structure for review or analysis.",
            do_not_use_when="The caller needs an official execution source.",
            subject_concepts=("craft.bop.version", "craft.execution_structure"),
            effects=("read:craft.bop.execution_structure",),
            tags=("craft", "bop", "execution_structure", "read"),
            input_schema={
                "type": "object",
                "required": ["version_gid", "expected_revision"],
                "properties": {
                    "version_gid": {"type": "string"},
                    "expected_revision": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            output_schema=_STRUCTURE_OUTPUT,
            **common,
        ),
        preview_execution_structure,
    )
    registry.register(
        CapabilitySpec(
            id="craft.bop.linked_parts.get",
            description="Read PBOM parts explicitly linked to a BOP and their usage locations.",
            use_when="The caller needs parts already used by a BOP.",
            do_not_use_when="The caller is searching PBOM candidate parts.",
            subject_concepts=("craft.bop.version", "craft.pbom.part"),
            effects=("read:craft.bop.linked_parts",),
            tags=("craft", "bop", "pbom", "part", "read"),
            input_schema={
                "type": "object",
                "required": ["version_gid"],
                "properties": {"version_gid": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["version_gid", "revision", "items"],
            },
            **common,
        ),
        get_linked_parts,
    )
    registry.register(
        CapabilitySpec(
            id="craft.bop.work_package.get",
            description="Project one BOP structure into a line, station or role work package.",
            use_when="The caller needs bounded execution context for one governed scope.",
            do_not_use_when="The caller needs the complete BOP structure.",
            subject_concepts=("craft.bop.version", "craft.work_package"),
            effects=("read:craft.bop.work_package",),
            tags=("craft", "bop", "work_package", "read"),
            input_schema={
                "type": "object",
                "required": ["version_gid", "scope"],
                "properties": {
                    "version_gid": {"type": "string"},
                    "scope": {"type": "object"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "version_gid",
                    "revision",
                    "scope",
                    "work_items",
                    "parts",
                    "tools",
                    "fixtures",
                    "equipment_requirements",
                    "knowledge_refs",
                    "rule_refs",
                ],
            },
            **common,
        ),
        get_work_package,
    )
