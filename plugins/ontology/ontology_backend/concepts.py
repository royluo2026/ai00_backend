"""Deterministic concept resolution over one immutable ontology release."""
from __future__ import annotations

from typing import Any, Mapping


def _fold(value: Any) -> str:
    return str(value or "").strip().casefold()


def concept_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("kind", "stable_gid", "external_id", "name", "label_zh", "label_en", "description", "deprecated")
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


def project_concept(item: Mapping[str, Any], view: str) -> dict[str, Any]:
    if view == "summary":
        return concept_summary(item)
    if view != "schema":
        raise ValueError("view must be summary or schema")
    excluded = {"created_at", "updated_at", "created_by", "object_sha256"}
    return {key: value for key, value in item.items() if key not in excluded}
