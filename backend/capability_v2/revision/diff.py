"""Canonical JSON normalization and domain-adapter diff contract."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, Protocol

from .canonical import canonical_json_bytes, normalize_json
from .models import Change


class DomainRevisionAdapter(Protocol):
    def normalize(self, content: Mapping[str, Any]) -> dict[str, Any]: ...
    def diff(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[Change, ...]: ...
    def validate_changeset(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> None: ...
    def apply_changeset(self, before: Mapping[str, Any], changes: Sequence[Change]) -> dict[str, Any]: ...
    def classify_conflict(self, path: str, base: Any, ours: Any, theirs: Any) -> str: ...


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _identity(item: Any) -> str | None:
    if not isinstance(item, Mapping):
        return None
    for field in ("stable_gid", "gid", "id", "key"):
        value = item.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _diff(before: Any, after: Any, path: str) -> list[Change]:
    if before == after:
        return []
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        changes: list[Change] = []
        for key in sorted(before.keys() | after.keys()):
            child = f"{path}/{_escape(key)}"
            if key not in before:
                changes.append(Change(change_type="add", path=child, after=deepcopy(after[key])))
            elif key not in after:
                changes.append(Change(change_type="remove", path=child, before=deepcopy(before[key])))
            else:
                changes.extend(_diff(before[key], after[key], child))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        old_ids = [_identity(item) for item in before]
        new_ids = [_identity(item) for item in after]
        if all(old_ids) and all(new_ids) and len(set(old_ids)) == len(old_ids) and len(set(new_ids)) == len(new_ids):
            old_by_id = dict(zip(old_ids, before, strict=True))
            new_by_id = dict(zip(new_ids, after, strict=True))
            changes = []
            for identity in sorted(set(old_ids) | set(new_ids)):
                if identity not in old_by_id:
                    changes.append(Change(change_type="add", path=path, after=deepcopy(new_by_id[identity]), identity=identity, to_index=new_ids.index(identity)))
                elif identity not in new_by_id:
                    changes.append(Change(change_type="remove", path=path, before=deepcopy(old_by_id[identity]), identity=identity, from_index=old_ids.index(identity)))
                else:
                    old_index, new_index = old_ids.index(identity), new_ids.index(identity)
                    if old_index != new_index:
                        changes.append(Change(change_type="move", path=path, identity=identity, from_index=old_index, to_index=new_index))
                    changes.extend(_diff(old_by_id[identity], new_by_id[identity], f"{path}/{_escape(identity)}"))
            return changes
    return [Change(change_type="replace", path=path or "/", before=deepcopy(before), after=deepcopy(after))]


class JsonDocumentAdapter:
    def normalize(self, content: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(content, Mapping):
            raise TypeError("revision root must be an object")
        return normalize_json(content)

    def diff(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[Change, ...]:
        return tuple(_diff(self.normalize(before), self.normalize(after), ""))

    def validate_changeset(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
        self.normalize(before)
        self.normalize(after)

    def apply_changeset(self, before: Mapping[str, Any], changes: Sequence[Change]) -> dict[str, Any]:
        document = deepcopy(self.normalize(before))

        def segments(path: str) -> list[str]:
            if path == "/":
                return []
            return [item.replace("~1", "/").replace("~0", "~") for item in path[1:].split("/")]

        def child(container: Any, segment: str) -> Any:
            if isinstance(container, dict):
                return container[segment]
            if isinstance(container, list):
                match = next((item for item in container if _identity(item) == segment), None)
                if match is None:
                    raise ValueError(f"changeset path identity not found: {segment}")
                return match
            raise ValueError("changeset path traverses a scalar")

        def target(path: str) -> Any:
            current = document
            for segment in segments(path):
                current = child(current, segment)
            return current

        for change in changes:
            path_segments = segments(change.path)
            if change.identity is not None:
                collection = target(change.path)
                if not isinstance(collection, list):
                    raise ValueError("identity change target must be an array")
                current_index = next(
                    (index for index, item in enumerate(collection) if _identity(item) == change.identity),
                    None,
                )
                if change.change_type == "add":
                    if current_index is not None:
                        raise ValueError("changeset adds an existing identity")
                    collection.insert(change.to_index if change.to_index is not None else len(collection), deepcopy(change.after))
                elif change.change_type == "remove":
                    if current_index is None:
                        raise ValueError("changeset removes a missing identity")
                    collection.pop(current_index)
                elif change.change_type == "move":
                    if current_index is None or change.to_index is None:
                        raise ValueError("changeset moves a missing identity")
                    item = collection.pop(current_index)
                    collection.insert(change.to_index, item)
                else:
                    raise ValueError("identity array changes support add, remove and move")
                continue
            if not path_segments:
                if change.change_type != "replace" or not isinstance(change.after, Mapping):
                    raise ValueError("revision root supports only object replacement")
                document = deepcopy(change.after)
                continue
            parent = document
            for segment in path_segments[:-1]:
                parent = child(parent, segment)
            key = path_segments[-1]
            if not isinstance(parent, dict):
                raise ValueError("field change parent must be an object")
            if change.change_type == "add":
                if key in parent:
                    raise ValueError("changeset adds an existing field")
                parent[key] = deepcopy(change.after)
            elif change.change_type == "remove":
                if key not in parent:
                    raise ValueError("changeset removes a missing field")
                del parent[key]
            elif change.change_type == "replace":
                if key not in parent:
                    raise ValueError("changeset replaces a missing field")
                parent[key] = deepcopy(change.after)
            else:
                raise ValueError("field changes do not support move")
        return self.normalize(document)

    def classify_conflict(self, path: str, base: Any, ours: Any, theirs: Any) -> str:
        if isinstance(base, list) or isinstance(ours, list) or isinstance(theirs, list):
            return "collection"
        if isinstance(base, Mapping) or isinstance(ours, Mapping) or isinstance(theirs, Mapping):
            return "object"
        return "field"
