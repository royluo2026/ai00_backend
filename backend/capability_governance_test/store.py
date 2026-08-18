"""Insert-only snapshot persistence with stable logical and major identities."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from backend.utils.gid import next_gid

from .models import (
    CapabilityProjection,
    ImmutableRecordError,
    ScannedCapability,
    SnapshotDocument,
    SnapshotEntry,
    SnapshotRecord,
)


class GovernanceStore(ABC):
    @abstractmethod
    def import_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        """Append a snapshot and project its stable identities."""

    def save_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        return self.import_snapshot(document)

    def replace_snapshot(self, snapshot_gid: int, document: SnapshotDocument) -> None:
        raise ImmutableRecordError("snapshot_records_are_insert_only")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_value(row: Any, name: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row[name]
    return row[index]


def _duplicate_key(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "duplicate" in text or "integrity" in text and "unique" in text


class MemoryGovernanceStore(GovernanceStore):
    """Thread-safe in-memory store used by governance tests and local projections."""

    def __init__(self, next_ids: Callable[[], int] = next_gid):
        self._next_ids = next_ids
        self._lock = RLock()
        self._logical_ids: dict[str, int] = {}
        self._major_ids: dict[tuple[int, int], int] = {}
        self._snapshots: dict[int, SnapshotRecord] = {}

    def import_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        with self._lock:
            projections = self._project_capabilities(document)
            scan_run_gid = self._next_ids()
            snapshot_gid = self._next_ids()
            entries = tuple(
                SnapshotEntry(**projection.__dict__, snapshot_entry_gid=self._next_ids())
                for projection in projections
            )
            node_gids = {node.canonical_key: self._next_ids() for node in document.nodes}
            record = SnapshotRecord(
                snapshot_gid=snapshot_gid,
                scan_run_gid=scan_run_gid,
                document=document,
                entries=entries,
                node_gids=node_gids,
                binding_gids=tuple(self._next_ids() for _ in document.bindings),
                relation_gids=tuple(self._next_ids() for _ in document.relations),
            )
            self._snapshots[snapshot_gid] = record
            return record

    def get_snapshot(self, snapshot_gid: int) -> SnapshotRecord | None:
        with self._lock:
            return self._snapshots.get(snapshot_gid)

    def _project_capabilities(self, document: SnapshotDocument) -> tuple[CapabilityProjection, ...]:
        projections: list[CapabilityProjection] = []
        seen: set[tuple[str, int]] = set()
        for capability in document.capabilities:
            key = (capability.capability_id, capability.major_version)
            if key in seen:
                raise ImmutableRecordError("duplicate_capability_major_in_snapshot")
            seen.add(key)
            capability_gid = self._logical_ids.get(capability.capability_id)
            if capability_gid is None:
                capability_gid = self._next_ids()
                self._logical_ids[capability.capability_id] = capability_gid
            major_key = (capability_gid, capability.major_version)
            capability_version_gid = self._major_ids.get(major_key)
            if capability_version_gid is None:
                capability_version_gid = self._next_ids()
                self._major_ids[major_key] = capability_version_gid
            projections.append(_projection(capability, capability_gid, capability_version_gid))
        return tuple(projections)


class SqlGovernanceStore(GovernanceStore):
    """DB-API persistence using only parameterized statements and one commit."""

    def __init__(self, connection: Any, next_ids: Callable[[], int] = next_gid):
        self._connection = connection
        self._next_ids = next_ids

    def import_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        cursor = self._connection.cursor()
        try:
            projections = tuple(self._resolve_projection(cursor, capability) for capability in document.capabilities)
            self._ensure_no_duplicate_majors(projections)
            created_at = _now()
            scan_run_gid = self._next_ids()
            snapshot_gid = self._next_ids()
            self._insert_scan_run(cursor, scan_run_gid, document, created_at)
            self._insert_snapshot(cursor, snapshot_gid, scan_run_gid, document, created_at)
            entries = self._insert_snapshot_entries(cursor, snapshot_gid, projections, document, created_at)
            node_gids = self._insert_nodes(cursor, snapshot_gid, document, created_at)
            binding_gids = self._insert_bindings(cursor, snapshot_gid, projections, node_gids, document)
            relation_gids = self._insert_relations(cursor, snapshot_gid, node_gids, document)
            self._update_mutable_projections(cursor, snapshot_gid, projections, created_at)
            record = SnapshotRecord(
                snapshot_gid=snapshot_gid, scan_run_gid=scan_run_gid, document=document,
                entries=entries, node_gids=node_gids, binding_gids=binding_gids, relation_gids=relation_gids,
            )
            self._connection.commit()
            return record
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def _resolve_projection(self, cursor: Any, capability: ScannedCapability) -> CapabilityProjection:
        capability_gid = self._resolve_logical_gid(cursor, capability)
        capability_version_gid = self._resolve_major_gid(cursor, capability_gid, capability)
        return _projection(capability, capability_gid, capability_version_gid)

    def _resolve_logical_gid(self, cursor: Any, capability: ScannedCapability) -> int:
        row = self._select_logical(cursor, capability.capability_id)
        if row is not None:
            return self._verify_logical(row, capability)
        candidate = self._next_ids()
        try:
            cursor.execute(
                "INSERT INTO workmanship_base_capability_entries "
                "(capability_gid, capability_id, owner_domain, current_major_version, current_lifecycle_status, first_seen_at, last_seen_at, row_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (candidate, capability.capability_id, capability.owner_domain, capability.major_version,
                 capability.lifecycle_status, _now(), _now(), 1),
            )
            return candidate
        except Exception as exc:
            if not _duplicate_key(exc):
                raise
            recovered = self._select_logical(cursor, capability.capability_id)
            if recovered is None:
                raise ImmutableRecordError("identity_conflict: logical capability was not recoverable") from exc
            return self._verify_logical(recovered, capability)

    def _resolve_major_gid(self, cursor: Any, capability_gid: int, capability: ScannedCapability) -> int:
        row = self._select_major(cursor, capability_gid, capability.major_version)
        if row is not None:
            return self._verify_major(row, capability_gid, capability.major_version)
        candidate = self._next_ids()
        try:
            cursor.execute(
                "INSERT INTO workmanship_base_capability_versions "
                "(capability_version_gid, capability_gid, major_version, semantic_class, business_effect, lifecycle_status, first_seen_snapshot_gid, latest_snapshot_gid, retired_at, row_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (candidate, capability_gid, capability.major_version, capability.semantic_class,
                 capability.business_effect, capability.lifecycle_status, None, None, None, 1),
            )
            return candidate
        except Exception as exc:
            if not _duplicate_key(exc):
                raise
            recovered = self._select_major(cursor, capability_gid, capability.major_version)
            if recovered is None:
                raise ImmutableRecordError("identity_conflict: major capability was not recoverable") from exc
            return self._verify_major(recovered, capability_gid, capability.major_version)

    @staticmethod
    def _select_logical(cursor: Any, capability_id: str) -> Any:
        cursor.execute(
            "SELECT capability_gid, capability_id, owner_domain FROM workmanship_base_capability_entries WHERE capability_id = %s",
            (capability_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def _select_major(cursor: Any, capability_gid: int, major_version: int) -> Any:
        cursor.execute(
            "SELECT capability_version_gid, capability_gid, major_version FROM workmanship_base_capability_versions "
            "WHERE capability_gid = %s AND major_version = %s",
            (capability_gid, major_version),
        )
        return cursor.fetchone()

    @staticmethod
    def _verify_logical(row: Any, capability: ScannedCapability) -> int:
        if _row_value(row, "capability_id", 1) != capability.capability_id:
            raise ImmutableRecordError("identity_conflict: logical capability mismatch")
        if isinstance(row, Mapping) and row.get("owner_domain") not in {None, capability.owner_domain}:
            raise ImmutableRecordError("identity_conflict: logical owner mismatch")
        return int(_row_value(row, "capability_gid", 0))

    @staticmethod
    def _verify_major(row: Any, capability_gid: int, major_version: int) -> int:
        if int(_row_value(row, "capability_gid", 1)) != capability_gid or int(_row_value(row, "major_version", 2)) != major_version:
            raise ImmutableRecordError("identity_conflict: major capability mismatch")
        return int(_row_value(row, "capability_version_gid", 0))

    @staticmethod
    def _ensure_no_duplicate_majors(projections: tuple[CapabilityProjection, ...]) -> None:
        keys = {(item.capability_id, item.major_version) for item in projections}
        if len(keys) != len(projections):
            raise ImmutableRecordError("duplicate_capability_major_in_snapshot")

    @staticmethod
    def _insert_scan_run(cursor: Any, scan_run_gid: int, document: SnapshotDocument, created_at: datetime) -> None:
        cursor.execute(
            "INSERT INTO workmanship_base_capability_scan_runs "
            "(scan_run_gid, environment_key, trigger_type, code_revision, catalog_release_id, requested_by_gid, idempotency_key, status, started_at, finished_at, error_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (scan_run_gid, "test-governance", "import", document.code_revision, document.product_release_id,
             0, document.snapshot_hash, "completed", created_at, created_at, None),
        )

    @staticmethod
    def _insert_snapshot(cursor: Any, snapshot_gid: int, scan_run_gid: int, document: SnapshotDocument, created_at: datetime) -> None:
        cursor.execute(
            "INSERT INTO workmanship_base_capability_snapshots "
            "(snapshot_gid, scan_run_gid, snapshot_hash, code_revision, catalog_release_id, descriptor_count, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (snapshot_gid, scan_run_gid, document.snapshot_hash, document.code_revision,
             document.product_release_id, len(document.capabilities), created_at),
        )

    def _insert_snapshot_entries(self, cursor: Any, snapshot_gid: int, projections: tuple[CapabilityProjection, ...], document: SnapshotDocument, created_at: datetime) -> tuple[SnapshotEntry, ...]:
        entries: list[SnapshotEntry] = []
        for projection, capability in zip(projections, document.capabilities, strict=True):
            snapshot_entry_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_snapshot_entries "
                "(snapshot_entry_gid, snapshot_gid, capability_version_gid, descriptor_hash, input_schema_hash, output_schema_hash, error_schema_hash, policy_hash, provider_hash, descriptor_json, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (snapshot_entry_gid, snapshot_gid, projection.capability_version_gid, capability.descriptor_hash,
                 capability.input_schema_hash, capability.output_schema_hash, capability.error_schema_hash,
                 capability.policy_hash, capability.provider_hash, _json(capability.to_json()), created_at),
            )
            entries.append(SnapshotEntry(**projection.__dict__, snapshot_entry_gid=snapshot_entry_gid))
        return tuple(entries)

    def _insert_nodes(self, cursor: Any, snapshot_gid: int, document: SnapshotDocument, created_at: datetime) -> dict[str, int]:
        nodes: dict[str, int] = {}
        for node in document.nodes:
            if node.canonical_key in nodes:
                raise ImmutableRecordError("duplicate_implementation_node_in_snapshot")
            node_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_implementation_nodes "
                "(implementation_node_gid, snapshot_gid, owner_domain, node_type, canonical_key, source_path, source_symbol, http_method, route_path, artifact_hash, metadata_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (node_gid, snapshot_gid, node.owner_domain, node.node_type, node.canonical_key, node.source_path,
                 node.source_symbol, node.http_method, node.route_path, node.artifact_hash, _json(node.to_json()["metadata"])),
            )
            nodes[node.canonical_key] = node_gid
        return nodes

    def _insert_bindings(self, cursor: Any, snapshot_gid: int, projections: tuple[CapabilityProjection, ...], node_gids: Mapping[str, int], document: SnapshotDocument) -> tuple[int, ...]:
        versions = {(item.capability_id, item.major_version): item.capability_version_gid for item in projections}
        result: list[int] = []
        for binding in document.bindings:
            version_gid = versions.get((binding.capability_id, binding.major_version))
            node_gid = node_gids.get(binding.node_canonical_key)
            if version_gid is None or node_gid is None:
                raise ImmutableRecordError("binding_references_unknown_snapshot_entity")
            binding_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_bindings "
                "(binding_gid, snapshot_gid, capability_version_gid, implementation_node_gid, binding_type, binding_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (binding_gid, snapshot_gid, version_gid, node_gid, binding.binding_type, binding.binding_hash),
            )
            result.append(binding_gid)
        return tuple(result)

    def _insert_relations(self, cursor: Any, snapshot_gid: int, node_gids: Mapping[str, int], document: SnapshotDocument) -> tuple[int, ...]:
        result: list[int] = []
        for relation in document.relations:
            from_gid = node_gids.get(relation.from_canonical_key)
            to_gid = node_gids.get(relation.to_canonical_key)
            if from_gid is None or to_gid is None:
                raise ImmutableRecordError("relation_references_unknown_snapshot_node")
            relation_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_implementation_relations "
                "(relation_gid, snapshot_gid, from_node_gid, to_node_gid, relation_type, relation_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (relation_gid, snapshot_gid, from_gid, to_gid, relation.relation_type, relation.relation_hash),
            )
            result.append(relation_gid)
        return tuple(result)

    @staticmethod
    def _update_mutable_projections(cursor: Any, snapshot_gid: int, projections: tuple[CapabilityProjection, ...], seen_at: datetime) -> None:
        for projection in projections:
            cursor.execute(
                "UPDATE workmanship_base_capability_entries SET current_major_version = %s, current_lifecycle_status = %s, last_seen_at = %s, row_version = row_version + 1 WHERE capability_gid = %s",
                (projection.major_version, projection.lifecycle_status, seen_at, projection.capability_gid),
            )
            cursor.execute(
                "UPDATE workmanship_base_capability_versions SET latest_snapshot_gid = %s, lifecycle_status = %s, row_version = row_version + 1 WHERE capability_version_gid = %s",
                (snapshot_gid, projection.lifecycle_status, projection.capability_version_gid),
            )


def _projection(capability: ScannedCapability, capability_gid: int, capability_version_gid: int) -> CapabilityProjection:
    return CapabilityProjection(
        capability_gid=capability_gid, capability_version_gid=capability_version_gid,
        capability_id=capability.capability_id, major_version=capability.major_version,
        owner_domain=capability.owner_domain, semantic_class=capability.semantic_class,
        business_effect=capability.business_effect, lifecycle_status=capability.lifecycle_status,
        descriptor_hash=capability.descriptor_hash,
    )


def _json(value: Any) -> str:
    from .fingerprint import canonical_json
    return canonical_json(value)


__all__ = ["GovernanceStore", "MemoryGovernanceStore", "SqlGovernanceStore"]
