"""Digital Model semantic adapter for the shared Revision kernel."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from backend.capability_v2.revision.models import Change
from backend.domain_ports.digital_model import ComponentRef


_ROOT_FIELDS = {"model_id", "version_id", "artifact_ref", "components"}
_COMPONENT_FIELDS = {
    "component_id", "parent_component_id", "name", "component_type", "geometry_summary",
}


def _normalize_component(value: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(value) - _COMPONENT_FIELDS
    if unknown:
        raise ValueError(f"unknown Digital Model component field: {sorted(unknown)[0]}")
    component_id = str(value.get("component_id") or "").strip()
    if not component_id:
        raise ValueError("component_id is required")
    geometry = value.get("geometry_summary") or {}
    if not isinstance(geometry, Mapping):
        raise ValueError("geometry_summary must be an object")
    return {
        "component_id": component_id,
        "parent_component_id": str(value.get("parent_component_id") or ""),
        "name": str(value.get("name") or component_id),
        "component_type": str(value.get("component_type") or "part"),
        "geometry_summary": {str(key): geometry[key] for key in sorted(geometry)},
    }


class DigitalModelRevisionAdapter:
    def normalize(self, content: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(content) - _ROOT_FIELDS
        if unknown:
            raise ValueError(f"unknown Digital Model snapshot field: {sorted(unknown)[0]}")
        model_id = str(content.get("model_id") or "").strip()
        version_id = str(content.get("version_id") or "").strip()
        artifact = content.get("artifact_ref")
        if not model_id or not version_id or not isinstance(artifact, Mapping):
            raise ValueError("model_id, version_id and artifact_ref are required")
        components = [_normalize_component(item) for item in content.get("components") or ()]
        ids = [item["component_id"] for item in components]
        if len(ids) != len(set(ids)):
            raise ValueError("component_id must be unique in a model snapshot")
        return {
            "model_id": model_id,
            "version_id": version_id,
            "artifact_ref": deepcopy(dict(artifact)),
            "components": sorted(components, key=lambda item: item["component_id"]),
        }

    def validate_changeset(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
        old, new = self.normalize(before), self.normalize(after)
        if old["model_id"] != new["model_id"]:
            raise ValueError("Digital Model revisions cannot change model identity")

    def diff(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[Change, ...]:
        old, new = self.normalize(before), self.normalize(after)
        changes: list[Change] = []
        if old["artifact_ref"] != new["artifact_ref"]:
            changes.append(Change(
                change_type="replace", path="/artifact_ref", before=old["artifact_ref"],
                after=new["artifact_ref"], identity=old["model_id"], breaking=True,
            ))
        old_components = {item["component_id"]: item for item in old["components"]}
        new_components = {item["component_id"]: item for item in new["components"]}
        for component_id in sorted(old_components.keys() | new_components.keys()):
            prior, current = old_components.get(component_id), new_components.get(component_id)
            path = f"/components/{component_id}"
            reference = ComponentRef(
                model_id=new["model_id"], version_id=new["version_id"], component_id=component_id,
            )
            if prior is None:
                changes.append(Change(change_type="add", path=path, after=current, identity=component_id, resource_ref=reference))
            elif current is None:
                changes.append(Change(change_type="remove", path=path, before=prior, identity=component_id, resource_ref=reference, breaking=True))
            elif prior["parent_component_id"] != current["parent_component_id"]:
                changes.append(Change(change_type="move", path=path + "/parent_component_id", before=prior["parent_component_id"], after=current["parent_component_id"], identity=component_id, resource_ref=reference))
            elif prior["geometry_summary"] != current["geometry_summary"]:
                changes.append(Change(change_type="geometry_change", path=path + "/geometry_summary", before=prior["geometry_summary"], after=current["geometry_summary"], identity=component_id, resource_ref=reference))
            elif prior != current:
                changes.append(Change(change_type="modify", path=path, before=prior, after=current, identity=component_id, resource_ref=reference))
        return tuple(changes)

    def apply_changeset(self, before: Mapping[str, Any], changes: Sequence[Change]) -> dict[str, Any]:
        result = self.normalize(before)
        components = {item["component_id"]: item for item in result["components"]}
        for change in changes:
            if change.path == "/artifact_ref" and change.change_type == "replace":
                result["artifact_ref"] = deepcopy(change.after)
                continue
            component_id = str(change.identity or "")
            if change.change_type == "remove":
                components.pop(component_id, None)
            elif change.change_type == "add":
                components[component_id] = _normalize_component(change.after)
            elif change.change_type == "move":
                components[component_id]["parent_component_id"] = str(change.after or "")
            elif change.change_type == "geometry_change":
                components[component_id]["geometry_summary"] = deepcopy(change.after)
            elif change.change_type == "modify":
                components[component_id] = _normalize_component(change.after)
            else:
                raise ValueError(f"unsupported Digital Model change: {change.change_type}")
        result["components"] = sorted(components.values(), key=lambda item: item["component_id"])
        return self.normalize(result)

    def classify_conflict(self, path: str, base: Any, ours: Any, theirs: Any) -> str:
        if path.endswith("/parent_component_id"):
            return "component_move"
        if path.endswith("/geometry_summary"):
            return "geometry_summary"
        return "digital_model_object"


__all__ = ["DigitalModelRevisionAdapter"]
