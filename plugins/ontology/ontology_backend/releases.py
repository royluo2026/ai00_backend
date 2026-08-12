"""Build immutable ontology release candidates from typed proposal changes."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def apply_changes(base: Sequence[Mapping[str, Any]], changes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    objects = {(str(item["kind"]), str(item["stable_gid"])): dict(item) for item in base}
    for change in changes:
        operation = str(change["operation"])
        stable_gid = str(change["stable_gid"])
        value = dict(change.get("value") or {})
        if operation == "parent.change":
            identity = ("concept", stable_gid)
            if identity not in objects:
                raise ValueError(f"parent.change target does not exist: {stable_gid}")
            objects[identity] = {**objects[identity], "parent_stable_gid": value.get("parent_stable_gid")}
            continue
        kind, action = operation.split(".", 1)
        identity = (kind, stable_gid)
        if action == "add":
            if identity in objects:
                raise ValueError(f"ontology object already exists: {kind}/{stable_gid}")
            objects[identity] = {**value, "kind": kind, "stable_gid": stable_gid}
        elif action == "change":
            if identity not in objects:
                raise ValueError(f"ontology object does not exist: {kind}/{stable_gid}")
            objects[identity] = {**objects[identity], **value, "kind": kind, "stable_gid": stable_gid}
        elif action == "deprecate":
            if identity not in objects:
                raise ValueError(f"ontology object does not exist: {kind}/{stable_gid}")
            objects[identity] = {**objects[identity], **value, "deprecated": True}
        else:
            raise ValueError(f"unsupported release operation: {operation}")
    return [objects[key] for key in sorted(objects)]
