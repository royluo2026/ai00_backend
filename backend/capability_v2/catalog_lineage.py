"""Authoritative order and compatibility metadata for immutable Catalog releases."""
from __future__ import annotations

import hashlib
import json
from typing import Iterable, Mapping

from pydantic import Field, model_validator

from .catalog import CatalogRelease, compatibility_errors
from .contracts import FrozenModel, LifecycleStatus


def _capability_key(capability_id: str, major_version: int) -> str:
    return f"{capability_id}@{major_version}"


class CatalogLineageEntry(FrozenModel):
    sequence: int = Field(ge=1)
    release_id: str = Field(pattern=r"^rel_[0-9a-f]{32}$")
    catalog_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    parent_release_id: str | None = Field(default=None, pattern=r"^rel_[0-9a-f]{32}$")
    compatible_with_parent: bool
    stable_schema_hashes: Mapping[str, str]


class CatalogLineage(FrozenModel):
    schema_version: int = 1
    entries: tuple[CatalogLineageEntry, ...]
    content_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_lineage(self) -> "CatalogLineage":
        if not self.entries:
            raise ValueError("catalog_lineage_empty")
        releases = set()
        for index, entry in enumerate(self.entries):
            if entry.sequence != index + 1:
                raise ValueError("catalog_lineage_sequence_invalid")
            if entry.release_id in releases:
                raise ValueError("catalog_lineage_release_duplicate")
            expected_parent = self.entries[index - 1].release_id if index else None
            if entry.parent_release_id != expected_parent:
                raise ValueError("catalog_lineage_parent_invalid")
            if index == 0 and not entry.compatible_with_parent:
                raise ValueError("catalog_lineage_root_invalid")
            releases.add(entry.release_id)
        if self.content_sha256 != _content_hash(self.entries):
            raise ValueError("catalog_lineage_hash_mismatch")
        return self

    @classmethod
    def from_releases(cls, releases: Iterable[CatalogRelease]) -> "CatalogLineage":
        ordered = tuple(releases)
        if not ordered:
            raise ValueError("catalog_lineage_empty")
        entries = []
        for index, release in enumerate(ordered):
            previous = ordered[index - 1] if index else None
            entries.append(CatalogLineageEntry(
                sequence=index + 1,
                release_id=release.release_id,
                catalog_hash=release.catalog_hash,
                parent_release_id=previous.release_id if previous else None,
                compatible_with_parent=(
                    True if previous is None else not compatibility_errors(previous, release)
                ),
                stable_schema_hashes={
                    _capability_key(item.id, item.major_version): item.schema_hash
                    for item in release.descriptors
                    if item.lifecycle_status is LifecycleStatus.STABLE
                },
            ))
        frozen = tuple(entries)
        return cls(entries=frozen, content_sha256=_content_hash(frozen))

    def append(
        self, previous_release: CatalogRelease, candidate_release: CatalogRelease,
    ) -> "CatalogLineage":
        latest = self.entries[-1]
        if latest.release_id != previous_release.release_id:
            raise ValueError("catalog_lineage_previous_release_mismatch")
        if latest.catalog_hash != previous_release.catalog_hash:
            raise ValueError("catalog_lineage_previous_hash_mismatch")
        if candidate_release.release_id == previous_release.release_id:
            if candidate_release.catalog_hash != previous_release.catalog_hash:
                raise ValueError("catalog_lineage_candidate_hash_mismatch")
            return self
        entry = CatalogLineageEntry(
            sequence=len(self.entries) + 1,
            release_id=candidate_release.release_id,
            catalog_hash=candidate_release.catalog_hash,
            parent_release_id=previous_release.release_id,
            compatible_with_parent=not compatibility_errors(
                previous_release, candidate_release
            ),
            stable_schema_hashes={
                _capability_key(item.id, item.major_version): item.schema_hash
                for item in candidate_release.descriptors
                if item.lifecycle_status is LifecycleStatus.STABLE
            },
        )
        entries = (*self.entries, entry)
        return CatalogLineage(entries=entries, content_sha256=_content_hash(entries))

    def require_floor(
        self,
        *,
        minimum_release_id: str,
        active_release_id: str,
        capability_id: str,
        major_version: int,
        active_schema_hash: str,
    ) -> None:
        positions = {entry.release_id: index for index, entry in enumerate(self.entries)}
        if minimum_release_id not in positions or active_release_id not in positions:
            raise ValueError("catalog_release_lineage_unavailable")
        minimum_index = positions[minimum_release_id]
        active_index = positions[active_release_id]
        if active_index < minimum_index:
            raise ValueError("catalog_release_floor_not_met")
        key = _capability_key(capability_id, major_version)
        minimum_hash = self.entries[minimum_index].stable_schema_hashes.get(key)
        active_hash = self.entries[active_index].stable_schema_hashes.get(key)
        if minimum_hash != active_schema_hash or active_hash != active_schema_hash:
            raise ValueError("catalog_release_incompatible")
        if any(
            not entry.compatible_with_parent
            for entry in self.entries[minimum_index + 1:active_index + 1]
        ):
            raise ValueError("catalog_release_incompatible")


def _content_hash(entries: Iterable[CatalogLineageEntry]) -> str:
    document = [entry.model_dump(mode="json") for entry in entries]
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


__all__ = ["CatalogLineage", "CatalogLineageEntry"]
