"""Public cross-domain Craft ports; implementations remain Craft-owned."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class BopVersionRef:
    object_ref: str
    revision: int
    content_hash: str | None


@dataclass(frozen=True)
class PbomSnapshotRef:
    object_ref: str
    project_ref: str | None


@dataclass(frozen=True)
class CraftChangeRef:
    object_ref: str
    base_revision: int
    before_hash: str
    after_hash: str


class CraftQueryPort(Protocol):
    def get_bop_version(self, object_ref: str, *, actor_id: str) -> BopVersionRef: ...
    def compare_bop_versions(self, before_ref: str, after_ref: str, *, actor_id: str) -> Mapping[str, object]: ...
    def get_pbom_snapshot(self, object_ref: str, *, actor_id: str) -> PbomSnapshotRef: ...


class CraftExecutionPlanPort(Protocol):
    """Version-pinned execution structure used by cross-domain orchestrators."""

    def get_execution_plan(
        self, reference: Mapping[str, Any], context: Any,
    ) -> Mapping[str, Any]: ...


class CraftCommandPort(Protocol):
    def preview_change(
        self,
        version_ref: str,
        *,
        expected_revision: int,
        commands: Sequence[Mapping[str, object]],
        actor_id: str,
    ) -> CraftChangeRef: ...


__all__ = [
    "BopVersionRef", "CraftChangeRef", "CraftCommandPort", "CraftExecutionPlanPort", "CraftQueryPort",
    "PbomSnapshotRef",
]
