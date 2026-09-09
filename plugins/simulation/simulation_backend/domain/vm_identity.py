"""Identity continuity rules for versioned VisMockup occurrence snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Literal

from backend.platform_sdk.ids import next_gid


OccurrenceKind = Literal["part", "tool", "fixture", "equipment", "socket"]
ChangeKind = Literal["unchanged", "moved", "added", "reloaded", "upgraded", "ambiguous"]


@dataclass(frozen=True)
class VmObservation:
    occurrence_gid: str | None
    source_instance_id: str
    session_gid: str
    kind: OccurrenceKind
    model_number: str
    bom_line: str
    revision: str
    catia_occurrence_name: str
    normalized_transform: tuple[str, ...]
    removed: bool = False


@dataclass(frozen=True)
class IdentityMatch:
    observation: VmObservation
    occurrence_gid: str
    change: ChangeKind
    predecessor_gid: str | None = None
    candidate_predecessor_gids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnapshotDiff:
    matches: tuple[IdentityMatch, ...]
    removed_occurrence_gids: tuple[str, ...]


def _new_gid(factory: Callable[[], str | int]) -> str:
    value = str(factory())
    if not value.isdecimal() or int(value) <= 0:
        raise ValueError("invalid_gid")
    return value


def _unique(items: Iterable[VmObservation], used: set[str]) -> VmObservation | None:
    candidates = [item for item in items if item.occurrence_gid and item.occurrence_gid not in used]
    return candidates[0] if len(candidates) == 1 else None


def diff_snapshots(
    previous: Iterable[VmObservation],
    current: Iterable[VmObservation],
    *,
    gid_factory: Callable[[], str | int] = next_gid,
) -> SnapshotDiff:
    """Assign persistent GIDs without treating transient VM node IDs as identity."""
    prior = tuple(previous)
    active = tuple(item for item in prior if not item.removed)
    removed = tuple(item for item in prior if item.removed)
    used: set[str] = set()
    matches: list[IdentityMatch] = []

    for incoming in current:
        candidate: VmObservation | None = None

        # A live VM occurrence is stable while its document session remains live.
        if incoming.catia_occurrence_name:
            candidate = _unique(
                (
                    item
                    for item in active
                    if item.kind == incoming.kind
                    and item.model_number == incoming.model_number
                    and item.session_gid == incoming.session_gid
                    and item.catia_occurrence_name == incoming.catia_occurrence_name
                ),
                used,
            )

        # Across exports, exact BOM line plus normalized pose is complete part identity.
        if candidate is None and incoming.kind == "part":
            candidate = _unique(
                (
                    item
                    for item in active
                    if item.kind == "part"
                    and item.bom_line == incoming.bom_line
                    and item.normalized_transform == incoming.normalized_transform
                ),
                used,
            )

        # A part that moved during dynamic simulation keeps identity when CATIA lineage agrees.
        if candidate is None and incoming.kind == "part" and incoming.catia_occurrence_name:
            candidate = _unique(
                (
                    item
                    for item in active
                    if item.kind == "part"
                    and item.model_number == incoming.model_number
                    and item.revision == incoming.revision
                    and item.catia_occurrence_name == incoming.catia_occurrence_name
                ),
                used,
            )

        if candidate is not None:
            assert candidate.occurrence_gid is not None
            if candidate.revision != incoming.revision:
                gid = _new_gid(gid_factory)
                matches.append(IdentityMatch(incoming, gid, "upgraded", candidate.occurrence_gid))
            else:
                used.add(candidate.occurrence_gid)
                change: ChangeKind = (
                    "unchanged"
                    if candidate.normalized_transform == incoming.normalized_transform
                    else "moved"
                )
                matches.append(IdentityMatch(incoming, candidate.occurrence_gid, change))
            continue

        lineage = [
            item
            for item in active
            if item.occurrence_gid not in used
            and item.kind == incoming.kind
            and item.model_number == incoming.model_number
            and (
                not incoming.catia_occurrence_name
                or item.catia_occurrence_name == incoming.catia_occurrence_name
            )
        ]
        upgraded = [item for item in lineage if item.revision != incoming.revision]
        if len(upgraded) == 1 and upgraded[0].occurrence_gid:
            matches.append(
                IdentityMatch(incoming, _new_gid(gid_factory), "upgraded", upgraded[0].occurrence_gid)
            )
            continue

        reload_candidates = [
            item
            for item in removed
            if item.kind == incoming.kind and item.model_number == incoming.model_number
        ]
        if len(reload_candidates) == 1 and reload_candidates[0].occurrence_gid:
            matches.append(
                IdentityMatch(
                    incoming,
                    _new_gid(gid_factory),
                    "reloaded",
                    reload_candidates[0].occurrence_gid,
                )
            )
            continue

        if incoming.kind == "part" and not incoming.catia_occurrence_name and len(lineage) > 1:
            matches.append(
                IdentityMatch(
                    incoming,
                    _new_gid(gid_factory),
                    "ambiguous",
                    candidate_predecessor_gids=tuple(
                        str(item.occurrence_gid) for item in lineage if item.occurrence_gid
                    ),
                )
            )
            continue

        matches.append(IdentityMatch(incoming, _new_gid(gid_factory), "added"))

    return SnapshotDiff(
        matches=tuple(matches),
        removed_occurrence_gids=tuple(
            str(item.occurrence_gid)
            for item in active
            if item.occurrence_gid and item.occurrence_gid not in used
        ),
    )


__all__ = ["IdentityMatch", "SnapshotDiff", "VmObservation", "diff_snapshots"]
