"""Deterministic, side-effect-free comparison of immutable VM observations."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from .vm_identity import VmObservation


@dataclass(frozen=True)
class VmDiffItem:
    change_type: str
    before_occurrence_gid: str | None
    after_occurrence_gid: str | None
    severity: str
    payload: dict


@dataclass(frozen=True)
class VmDiff:
    algorithm_version: str
    items: tuple[VmDiffItem, ...]
    summary: dict[str, int]


_CHANGES = (
    ("revision_upgraded", "revision"),
    ("representation_replaced", "representation_locations"),
    ("geometry_content_changed", "geometry_hash"),
    ("moved", "parent_path"),
    ("reordered", "order_index"),
    ("renamed", "catia_occurrence_name"),
    ("attributes_changed", "attributes"),
)
_RANK = {name: index for index, (name, _) in enumerate(_CHANGES)} | {
    "ambiguous_identity": 7, "removed": 8, "added": 9,
}


def _gid(value) -> str | None:
    return str(value) if value not in (None, "") else None


def _item(change_type: str, before: VmObservation | None, after: VmObservation | None, **extra) -> VmDiffItem:
    payload = {
        "before_parent": list(before.parent_path) if before else None,
        "after_parent": list(after.parent_path) if after else None,
        "before_order": before.order_index if before else None,
        "after_order": after.order_index if after else None,
        "before_revision": before.revision if before else None,
        "after_revision": after.revision if after else None,
        "before_representation": list(before.representation_locations) if before else None,
        "after_representation": list(after.representation_locations) if after else None,
        "before_geometry_hash": before.geometry_hash if before else None,
        "after_geometry_hash": after.geometry_hash if after else None,
        **extra,
    }
    return VmDiffItem(change_type, _gid(before.occurrence_gid) if before else None,
                      _gid(after.occurrence_gid) if after else None,
                      "warning" if change_type in {"ambiguous_identity", "removed"} else "info", payload)


def compare_vm_snapshots(before: Iterable[VmObservation], after: Iterable[VmObservation], *, algorithm_version: str) -> VmDiff:
    prior = tuple(before)
    current = tuple(after)
    by_gid = {_gid(row.occurrence_gid): row for row in prior if _gid(row.occurrence_gid)}
    by_source = defaultdict(list)
    for row in prior:
        by_source[row.source_instance_id].append(row)
    matched: set[str] = set()
    items: list[VmDiffItem] = []
    for incoming in sorted(current, key=lambda row: (_gid(row.occurrence_gid) or "", row.source_instance_id)):
        incoming_gid = _gid(incoming.occurrence_gid)
        previous = by_gid.get(incoming_gid) if incoming_gid else None
        if previous is None:
            candidates = [row for row in by_source[incoming.source_instance_id]
                          if _gid(row.occurrence_gid) not in matched]
            if len(candidates) > 1:
                items.append(_item("ambiguous_identity", None, incoming,
                    candidate_occurrence_gids=sorted(_gid(row.occurrence_gid) for row in candidates)))
                continue
            if len(candidates) == 1:
                previous = candidates[0]
        if previous is None:
            items.append(_item("added", None, incoming))
            continue
        if _gid(previous.occurrence_gid):
            matched.add(_gid(previous.occurrence_gid))
        for change_type, field in _CHANGES:
            if getattr(previous, field) != getattr(incoming, field):
                items.append(_item(change_type, previous, incoming))
    for previous in prior:
        if _gid(previous.occurrence_gid) not in matched:
            items.append(_item("removed", previous, None))
    items.sort(key=lambda row: (_RANK[row.change_type], row.before_occurrence_gid or "", row.after_occurrence_gid or ""))
    counts = Counter(item.change_type for item in items)
    return VmDiff(str(algorithm_version), tuple(items), {key: counts[key] for key in sorted(counts)})


__all__ = ["VmDiff", "VmDiffItem", "compare_vm_snapshots"]
