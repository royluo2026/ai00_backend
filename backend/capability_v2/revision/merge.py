"""Deterministic three-way merge independent of business-domain semantics."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .diff import DomainRevisionAdapter
from .models import MergeConflict


_MISSING = object()


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _public(value: Any) -> Any:
    return None if value is _MISSING else deepcopy(value)


def three_way_merge(
    base: Mapping[str, Any],
    ours: Mapping[str, Any],
    theirs: Mapping[str, Any],
    adapter: DomainRevisionAdapter,
) -> tuple[dict[str, Any] | None, tuple[MergeConflict, ...]]:
    conflicts: list[MergeConflict] = []

    def merge_value(base_value: Any, our_value: Any, their_value: Any, path: str) -> Any:
        if our_value == their_value:
            return deepcopy(our_value)
        if our_value == base_value:
            return deepcopy(their_value)
        if their_value == base_value:
            return deepcopy(our_value)
        values = (base_value, our_value, their_value)
        if all(value is _MISSING or isinstance(value, Mapping) for value in values):
            merged: dict[str, Any] = {}
            keys: set[str] = set()
            for value in values:
                if isinstance(value, Mapping):
                    keys.update(value)
            for key in sorted(keys):
                b = base_value.get(key, _MISSING) if isinstance(base_value, Mapping) else _MISSING
                o = our_value.get(key, _MISSING) if isinstance(our_value, Mapping) else _MISSING
                t = their_value.get(key, _MISSING) if isinstance(their_value, Mapping) else _MISSING
                child = merge_value(b, o, t, f"{path}/{_escape(key)}")
                if child is not _MISSING:
                    merged[key] = child
            return merged
        conflicts.append(MergeConflict(
            path=path or "/",
            kind=adapter.classify_conflict(path or "/", _public(base_value), _public(our_value), _public(their_value)),
            base=_public(base_value),
            ours=_public(our_value),
            theirs=_public(their_value),
        ))
        return deepcopy(our_value)

    merged = merge_value(adapter.normalize(base), adapter.normalize(ours), adapter.normalize(theirs), "")
    return (None if conflicts else merged), tuple(conflicts)
