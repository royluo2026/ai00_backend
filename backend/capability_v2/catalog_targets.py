"""Resolve governed targets against the versioned Capability Catalog."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class TargetResolution:
    ok: bool
    capability_id: str
    major_version: int
    reason_code: str | None = None
    actual_owner: str | None = None
    lifecycle: str | None = None


class CatalogTargetIndex:
    def __init__(
        self,
        targets: Mapping[tuple[str, int], tuple[str | None, str | None]],
        replacements: Mapping[tuple[str, int], str],
    ) -> None:
        self._targets = dict(targets)
        self._replacements = dict(replacements)

    @classmethod
    def from_catalog(
        cls,
        payload: Mapping[str, object],
        *,
        replacements: Mapping[tuple[str, int], str] | None = None,
    ) -> "CatalogTargetIndex":
        entries = payload.get("capabilities")
        if not isinstance(entries, list):
            raise ValueError("Catalog capabilities must be an array")
        targets: dict[tuple[str, int], tuple[str | None, str | None]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError("Catalog capability must be an object")
            capability_id = entry.get("id")
            major_version = entry.get("major_version", 1)
            if not isinstance(capability_id, str) or not capability_id:
                raise ValueError("Catalog capability ID is invalid")
            if not isinstance(major_version, int) or major_version < 1:
                raise ValueError(f"Catalog capability version is invalid: {capability_id}")
            key = (capability_id, major_version)
            if key in targets:
                raise ValueError(f"duplicate Catalog target: {capability_id}@{major_version}")
            owner = entry.get("owner_domain", entry.get("owner"))
            lifecycle = entry.get("lifecycle_status", entry.get("lifecycle"))
            targets[key] = (
                owner if isinstance(owner, str) and owner else None,
                lifecycle if isinstance(lifecycle, str) and lifecycle else None,
            )
        return cls(targets, replacements or {})

    def resolve_stable(
        self,
        capability_id: str,
        major_version: int,
        expected_owner: str,
    ) -> TargetResolution:
        target = self._targets.get((capability_id, major_version))
        if target is None:
            return TargetResolution(False, capability_id, major_version, "target_missing")
        actual_owner, lifecycle = target
        if lifecycle != "stable":
            return TargetResolution(
                False, capability_id, major_version, "target_not_stable", actual_owner, lifecycle
            )
        if actual_owner != expected_owner:
            return TargetResolution(
                False, capability_id, major_version, "target_owner_mismatch", actual_owner, lifecycle
            )
        if (capability_id, major_version) in self._replacements:
            return TargetResolution(
                False, capability_id, major_version, "target_replaced", actual_owner, lifecycle
            )
        return TargetResolution(True, capability_id, major_version, actual_owner=actual_owner, lifecycle=lifecycle)


__all__ = ["CatalogTargetIndex", "TargetResolution"]
