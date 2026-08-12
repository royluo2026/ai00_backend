"""Honest deterministic mapping assessment; this module never persists mappings."""
from __future__ import annotations

from typing import Any, Mapping


def assess_objects(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    existing_mappings: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    source_gid = str(source.get("stable_gid") or "").strip()
    target_gid = str(target.get("stable_gid") or "").strip()
    if not source_gid or not target_gid:
        return {
            "conclusion": "expert_review_required",
            "reasons": ["Stable source and target identities are required; names alone are not semantic evidence."],
            "checks": {},
        }
    source_kind = str(source.get("kind") or "").strip()
    target_kind = str(target.get("kind") or "").strip()
    checks: dict[str, Any] = {
        "source_identity": source_gid,
        "target_identity": target_gid,
        "kind_match": source_kind == target_kind,
    }
    if not source_kind or not target_kind:
        return {"conclusion": "expert_review_required", "reasons": ["Both object kinds are required."], "checks": checks}
    if source_kind != target_kind:
        return {"conclusion": "incompatible", "reasons": ["Ontology object kinds differ."], "checks": checks}
    mappings = existing_mappings or []
    conflicts = [
        item for item in mappings
        if str(item.get("source_stable_gid") or "") == source_gid
        and str(item.get("target_stable_gid") or "") not in {"", target_gid}
    ]
    checks["existing_mapping_unique"] = not conflicts
    if conflicts:
        return {"conclusion": "incompatible", "reasons": ["The source already maps to a different stable target."], "checks": checks}
    graph: dict[str, set[str]] = {}
    for item in mappings:
        left = str(item.get("source_stable_gid") or "")
        right = str(item.get("target_stable_gid") or "")
        if left and right:
            graph.setdefault(left, set()).add(right)
    pending = [target_gid]
    visited: set[str] = set()
    while pending:
        node = pending.pop()
        if node == source_gid:
            checks["mapping_cycle"] = True
            return {"conclusion": "incompatible", "reasons": ["The proposed mapping creates a cycle."], "checks": checks}
        if node not in visited:
            visited.add(node)
            pending.extend(graph.get(node, ()))
    checks["mapping_cycle"] = False
    if source.get("deprecated") or target.get("deprecated"):
        return {"conclusion": "expert_review_required", "reasons": ["A deprecated object requires expert disposition."], "checks": checks}
    if source_gid == target_gid:
        return {"conclusion": "compatible", "reasons": ["Both references identify the same stable ontology object."], "checks": checks}

    if source_kind == "property":
        source_type = source.get("value_type") or source.get("data_type")
        target_type = target.get("value_type") or target.get("data_type")
        source_cardinality = source.get("cardinality")
        target_cardinality = target.get("cardinality")
        checks.update({
            "value_type_match": bool(source_type and target_type and source_type == target_type),
            "cardinality_match": bool(source_cardinality and target_cardinality and source_cardinality == target_cardinality),
        })
        if source_type and target_type and source_type != target_type:
            return {"conclusion": "incompatible", "reasons": ["Property value types differ."], "checks": checks}
        if source_cardinality and target_cardinality and source_cardinality != target_cardinality:
            return {"conclusion": "incompatible", "reasons": ["Property cardinalities differ."], "checks": checks}
        if checks["value_type_match"] and checks["cardinality_match"]:
            return {"conclusion": "compatible", "reasons": ["Property type and cardinality contracts match."], "checks": checks}
    elif source_kind == "relation":
        roles = ("domain_stable_gid", "range_stable_gid")
        checks["relation_roles_match"] = all(source.get(key) and source.get(key) == target.get(key) for key in roles)
        if any(source.get(key) and target.get(key) and source.get(key) != target.get(key) for key in roles):
            return {"conclusion": "incompatible", "reasons": ["Relation domain or range roles differ."], "checks": checks}
        if checks["relation_roles_match"]:
            return {"conclusion": "compatible", "reasons": ["Relation role contracts match."], "checks": checks}

    return {
        "conclusion": "expert_review_required",
        "reasons": ["Deterministic checks are insufficient to establish semantic equivalence."],
        "checks": checks,
    }
