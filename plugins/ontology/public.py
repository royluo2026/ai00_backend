"""Versioned public read port over the immutable active Ontology release."""
from __future__ import annotations

from typing import Iterable

from .ontology_backend.repository import OntologyReleaseRepository


def _active_objects(kinds: set[str]) -> list[dict]:
    repository = OntologyReleaseRepository()
    release = repository.resolve_release()
    return repository.list_objects(str(release["release_gid"]), kinds)


def concept_labels(stable_gids: Iterable[str]) -> dict[str, str]:
    wanted = {str(gid) for gid in stable_gids if gid}
    return {
        str(item["stable_gid"]): str(item.get("label_zh") or item.get("name") or "")
        for item in _active_objects({"concept"})
        if str(item.get("stable_gid")) in wanted
    }


def concept(stable_gid: str) -> dict | None:
    for item in _active_objects({"concept"}):
        if str(item.get("stable_gid")) == str(stable_gid):
            return item
    return None


def properties(stable_gids: Iterable[str]) -> dict[str, dict]:
    wanted = {str(gid) for gid in stable_gids if gid}
    return {
        str(item["stable_gid"]): item
        for item in _active_objects({"property"})
        if str(item.get("stable_gid")) in wanted
    }


def active_projection() -> dict[str, list[dict]]:
    objects = _active_objects({"concept", "property", "relation", "constraint"})
    return {
        kind: [item for item in objects if item.get("kind") == kind]
        for kind in ("concept", "property", "relation", "constraint")
    }


__all__ = ["active_projection", "concept", "concept_labels", "properties"]
