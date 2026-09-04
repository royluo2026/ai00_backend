"""Deterministic concept resolution over one immutable ontology release."""
from __future__ import annotations

from typing import Any, Mapping


def _fold(value: Any) -> str:
    return str(value or "").strip().casefold()


def concept_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "kind", "stable_gid", "external_id", "node_type_binding", "name",
            "label_zh", "label_en", "description", "deprecated",
        )
        if item.get(key) is not None
    }


def resolve_term(term: str, objects: list[dict[str, Any]]) -> dict[str, Any]:
    needle = _fold(term)
    if not needle:
        raise ValueError("term is required")

    stable = [item for item in objects if _fold(item.get("stable_gid")) == needle]
    if len(stable) == 1:
        return {"status": "resolved", "matched_by": "stable_gid", "concept": stable[0], "candidates": []}

    external = [item for item in objects if item.get("external_id") and _fold(item.get("external_id")) == needle]
    if len(external) == 1:
        return {"status": "resolved", "matched_by": "external_id", "concept": external[0], "candidates": []}
    if len(external) > 1:
        return {"status": "ambiguous", "matched_by": "external_id", "concept": None, "candidates": external}

    node_type = [
        item for item in objects
        if item.get("node_type_binding") and _fold(item.get("node_type_binding")) == needle
    ]
    if len(node_type) == 1:
        return {
            "status": "resolved", "matched_by": "node_type_binding",
            "concept": node_type[0], "candidates": [],
        }
    if len(node_type) > 1:
        return {
            "status": "ambiguous", "matched_by": "node_type_binding",
            "concept": None, "candidates": node_type,
        }

    exact = []
    for item in objects:
        names = [item.get("name"), item.get("label_zh"), item.get("label_en"), *(item.get("aliases") or [])]
        if needle in {_fold(value) for value in names if value}:
            exact.append(item)
    if len(exact) == 1:
        return {"status": "resolved", "matched_by": "name_or_alias", "concept": exact[0], "candidates": []}
    if len(exact) > 1:
        return {"status": "ambiguous", "matched_by": "name_or_alias", "concept": None, "candidates": exact}

    fuzzy = []
    for item in objects:
        values = [item.get("name"), item.get("label_zh"), item.get("label_en"), *(item.get("aliases") or [])]
        if any(needle in _fold(value) or _fold(value) in needle for value in values if value):
            fuzzy.append(item)
    return {
        "status": "candidates" if fuzzy else "unresolved",
        "matched_by": "fuzzy_candidate" if fuzzy else None,
        "concept": None,
        "candidates": fuzzy[:20],
    }


def project_concept(
    item: Mapping[str, Any], view: str, objects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if view == "summary":
        return concept_summary(item)
    if view != "schema":
        raise ValueError("view must be summary or schema")
    excluded = {"created_at", "updated_at", "created_by", "object_sha256"}
    projected = {key: value for key, value in item.items() if key not in excluded}
    if item.get("kind") != "concept" or objects is None:
        return projected

    concepts = {
        str(candidate.get("stable_gid")): candidate
        for candidate in objects if candidate.get("kind") == "concept" and candidate.get("stable_gid")
    }
    lineage: list[str] = []
    current: Mapping[str, Any] | None = item
    visited: set[str] = set()
    while current is not None:
        gid = str(current.get("stable_gid") or "")
        if not gid or gid in visited:
            break
        visited.add(gid)
        lineage.append(gid)
        current = concepts.get(str(current.get("parent_gid") or ""))
    lineage.reverse()

    def related(kind: str, owner_key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for owner_gid in lineage:
            matches = [
                candidate for candidate in objects
                if candidate.get("kind") == kind and str(candidate.get(owner_key) or "") == owner_gid
            ]
            matches.sort(key=lambda row: (int(row.get("sort_order") or 0), str(row.get("name") or "")))
            rows.extend({key: value for key, value in row.items() if key not in excluded} for row in matches)
        return rows

    projected["properties"] = related("property", "class_gid")
    projected["relations"] = related("relation", "domain_class_gid")
    projected.setdefault("rules", [])
    return projected
