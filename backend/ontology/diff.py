"""Semantic ontology release diff by stable identity."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

CATEGORIES = {
    "concept": "concepts", "property": "properties", "relation": "relations",
    "mapping": "mappings", "constraint": "constraints",
}


def semantic_diff(before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    old = {(str(item.get("kind")), str(item.get("stable_gid"))): dict(item) for item in before}
    new = {(str(item.get("kind")), str(item.get("stable_gid"))): dict(item) for item in after}
    result = {name: {"added": [], "changed": [], "deprecated": [], "removed": []} for name in CATEGORIES.values()}
    for identity in sorted(old.keys() | new.keys()):
        kind, stable_gid = identity
        category = CATEGORIES.get(kind)
        if not category:
            continue
        prior = old.get(identity)
        current = new.get(identity)
        if prior is None:
            result[category]["added"].append(current)
        elif current is None:
            result[category]["removed"].append(prior)
        elif prior != current:
            change = {"stable_gid": stable_gid, "before": prior, "after": current}
            if not prior.get("deprecated") and current.get("deprecated"):
                result[category]["deprecated"].append(change)
            else:
                result[category]["changed"].append(change)
    breaking = any(value["removed"] or value["deprecated"] for value in result.values())
    structural = any(result[name]["changed"] for name in ("properties", "relations", "constraints"))
    result["compatibility"] = "breaking" if breaking else "migration_required" if structural else "backward_compatible"
    return result
