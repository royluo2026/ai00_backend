"""Semantic comparison of two BOP version structures."""
from __future__ import annotations
from typing import Any

from backend.capabilities.models_next import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from ..services.execution_structure import _normalize, repository


def compare_bop_versions(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    from_gid = payload.get("from_version_gid"); to_gid = payload.get("to_version_gid")
    if not isinstance(from_gid, str) or not from_gid: raise ValueError("from_version_gid is required")
    if not isinstance(to_gid, str) or not to_gid: raise ValueError("to_version_gid is required")
    before_aggregate = repository.load_bop_aggregate(from_gid, expected_revision=None)
    after_aggregate = repository.load_bop_aggregate(to_gid, expected_revision=None)
    before = _normalize(before_aggregate); after = _normalize(after_aggregate)
    left = {node["node_id"]: node for node in before["nodes"]}; right = {node["node_id"]: node for node in after["nodes"]}
    common = sorted(set(left) & set(right)); moved = []; changed = []
    for gid in common:
        if left[gid].get("parent_id") != right[gid].get("parent_id") or left[gid].get("sequence") != right[gid].get("sequence"):
            moved.append({"node_id": gid, "from_parent_id": left[gid].get("parent_id"), "to_parent_id": right[gid].get("parent_id"), "from_sequence": left[gid].get("sequence"), "to_sequence": right[gid].get("sequence")})
        fields = {name: {"before": left[gid].get(name), "after": right[gid].get(name)} for name in ("kind", "name", "vpps", "part_refs", "tool_refs", "fixture_refs", "equipment_refs", "knowledge_refs", "rule_refs") if left[gid].get(name) != right[gid].get(name)}
        if fields: changed.append({"node_id": gid, "fields": fields})
    data = {
        "comparability": "same_project" if before["source"]["project_gid"] == after["source"]["project_gid"] else "different_project",
        "from_version_gid": from_gid, "to_version_gid": to_gid,
        "added": [right[key] for key in sorted(set(right) - set(left))],
        "removed": [left[key] for key in sorted(set(left) - set(right))],
        "moved": moved, "changed": changed,
    }
    evidence = (
        EvidenceRef(kind="craft.bop.version", reference=f"craft://bop/version/{from_gid}", summary="Comparison base"),
        EvidenceRef(kind="craft.bop.version", reference=f"craft://bop/version/{to_gid}", summary="Comparison target"),
    )
    return CapabilityOutput(data=data, evidence=evidence)


def register_bop_compare_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.version.compare", owner="craft", description="Compare two BOP versions as semantic structure changes.",
        use_when="The caller needs additions, removals, moves and field changes.", do_not_use_when="A raw database JSON diff is requested.",
        subject_concepts=("craft.bop.version",), effects=("read:craft.bop.version.compare",), plugin_callable=True,
        input_schema={"type": "object", "required": ["from_version_gid", "to_version_gid"]},
        output_schema={"type": "object", "required": ["comparability", "added", "removed", "moved", "changed"]},
        tags=("craft", "bop", "version", "compare", "read")), compare_bop_versions)
