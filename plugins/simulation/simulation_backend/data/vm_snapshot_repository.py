"""Tenant- and owner-scoped persistence for VisMockup snapshot projections."""
from __future__ import annotations

from collections.abc import Callable, Iterable
import hashlib
import json

from backend.platform_sdk.ids import next_gid

from .connection import get_simulation_conn
from ..domain.vm_identity import SnapshotDiff


class VmRepositoryError(RuntimeError):
    pass


def _gid(value: str | int) -> str:
    text = str(value)
    if not text.isdecimal() or int(text) <= 0:
        raise ValueError("invalid_gid")
    return text


class VmSnapshotRepository:
    def __init__(
        self,
        connection_factory: Callable = get_simulation_conn,
        *,
        gid_factory: Callable[[], str | int] = next_gid,
    ) -> None:
        self._connection_factory = connection_factory
        self._gid_factory = gid_factory

    def create_document(
        self,
        *,
        workspace_gid: str,
        tenant_gid: str,
        owner_gid: str,
        source_kind: str,
        source_identity_hash: str,
    ) -> str:
        document_gid = _gid(self._gid_factory())
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_vm_documents "
                "(gid,workspace_gid,tenant_gid,owner_gid,source_kind,source_identity_hash) "
                "SELECT %s,%s,%s,%s,%s,%s FROM workmanship_sim_workspaces "
                "WHERE gid=%s AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL",
                (
                    document_gid,
                    _gid(workspace_gid),
                    _gid(tenant_gid),
                    _gid(owner_gid),
                    str(source_kind),
                    str(source_identity_hash),
                    _gid(workspace_gid),
                    _gid(tenant_gid),
                    _gid(owner_gid),
                ),
            )
            if cursor.rowcount != 1:
                raise VmRepositoryError("workspace_not_found")
        return document_gid

    def advance_head(
        self,
        *,
        document_gid: str,
        snapshot_gid: str,
        tenant_gid: str,
        owner_gid: str,
        expected_row_version: int,
    ) -> None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT h.row_version FROM workmanship_sim_vm_documents d "
                "LEFT JOIN workmanship_sim_vm_snapshot_heads h ON h.document_gid=d.gid "
                "WHERE d.gid=%s AND d.tenant_gid=%s AND d.owner_gid=%s "
                "AND d.removed_at IS NULL FOR UPDATE",
                (_gid(document_gid), _gid(tenant_gid), _gid(owner_gid)),
            )
            row = cursor.fetchone()
            if row is None:
                raise VmRepositoryError("vm_document_not_found")
            current = int(row.get("row_version") or 0)
            if current != expected_row_version:
                raise VmRepositoryError("version_conflict")
            if current == 0:
                cursor.execute(
                    "INSERT INTO workmanship_sim_vm_snapshot_heads "
                    "(document_gid,snapshot_gid,row_version) VALUES (%s,%s,1)",
                    (_gid(document_gid), _gid(snapshot_gid)),
                )
            else:
                cursor.execute(
                    "UPDATE workmanship_sim_vm_snapshot_heads SET snapshot_gid=%s,"
                    "row_version=row_version+1,updated_at=NOW(6) "
                    "WHERE document_gid=%s AND row_version=%s",
                    (_gid(snapshot_gid), _gid(document_gid), expected_row_version),
                )
            if cursor.rowcount != 1:
                raise VmRepositoryError("version_conflict")

    def soft_remove_occurrences(
        self,
        *,
        document_gid: str,
        occurrence_gids: Iterable[str],
        tenant_gid: str,
        owner_gid: str,
    ) -> int:
        gids = tuple(_gid(value) for value in occurrence_gids)
        if not gids:
            return 0
        placeholders = ",".join("%s" for _ in gids)
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_vm_occurrences SET status='removed',"
                "removed_at=NOW(6),row_version=row_version+1,updated_at=NOW(6) "
                "WHERE document_gid=%s AND tenant_gid=%s AND owner_gid=%s "
                f"AND gid IN ({placeholders}) AND removed_at IS NULL",
                (_gid(document_gid), _gid(tenant_gid), _gid(owner_gid), *gids),
            )
            return int(cursor.rowcount)

    def persist_snapshot(
        self,
        *,
        document_gid: str,
        session_gid: str,
        tenant_gid: str,
        owner_gid: str,
        sequence: int,
        artifact_gid: str,
        artifact_sha256: str,
        artifact_byte_size: int,
        snapshot_hash: str,
        parser_algorithm_version: str,
        identity_algorithm_version: str,
        captured_at: str,
        expected_head_row_version: int,
        diff: SnapshotDiff,
    ) -> dict[str, str | int]:
        """Persist one accepted projection and advance its document head in one transaction."""
        snapshot_gid = _gid(self._gid_factory())
        document_gid = _gid(document_gid)
        session_gid = _gid(session_gid)
        tenant_gid = _gid(tenant_gid)
        owner_gid = _gid(owner_gid)
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT h.row_version FROM workmanship_sim_vm_documents d "
                "LEFT JOIN workmanship_sim_vm_snapshot_heads h ON h.document_gid=d.gid "
                "WHERE d.gid=%s AND d.tenant_gid=%s AND d.owner_gid=%s "
                "AND d.removed_at IS NULL FOR UPDATE",
                (document_gid, tenant_gid, owner_gid),
            )
            row = cursor.fetchone()
            if row is None:
                raise VmRepositoryError("vm_document_not_found")
            current_head_version = int(row.get("row_version") or 0)
            if current_head_version != expected_head_row_version:
                raise VmRepositoryError("version_conflict")

            cursor.execute(
                "INSERT INTO workmanship_sim_vm_snapshots "
                "(gid,document_gid,session_gid,tenant_gid,owner_gid,sequence,artifact_gid,"
                "artifact_sha256,artifact_byte_size,snapshot_hash,parser_algorithm_version,"
                "identity_algorithm_version,captured_at) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    snapshot_gid, document_gid, session_gid, tenant_gid, owner_gid,
                    int(sequence), _gid(artifact_gid), artifact_sha256, int(artifact_byte_size),
                    snapshot_hash, parser_algorithm_version, identity_algorithm_version, captured_at,
                ),
            )

            for match in diff.matches:
                observation = match.observation
                occurrence_gid = _gid(match.occurrence_gid)
                if match.change in {"added", "reloaded", "upgraded", "ambiguous"}:
                    cursor.execute(
                        "INSERT INTO workmanship_sim_vm_occurrences "
                        "(gid,document_gid,tenant_gid,owner_gid,predecessor_gid,kind,model_number,first_session_gid) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            occurrence_gid, document_gid, tenant_gid, owner_gid,
                            _gid(match.predecessor_gid) if match.predecessor_gid else None,
                            observation.kind, observation.model_number, session_gid,
                        ),
                    )
                transform_json = json.dumps(observation.normalized_transform, separators=(",", ":"))
                cursor.execute(
                    "INSERT INTO workmanship_sim_vm_observations "
                    "(snapshot_gid,occurrence_gid,source_instance_id,bom_line,revision_code,"
                    "catia_occurrence_name,parent_path_json,normalized_transform_json,raw_transform_json,"
                    "representation_locations_json,change_kind) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        snapshot_gid, occurrence_gid, observation.source_instance_id,
                        observation.bom_line, observation.revision, observation.catia_occurrence_name,
                        "[]", transform_json, transform_json, "[]", match.change,
                    ),
                )
                pose_gid = _gid(self._gid_factory())
                pose_hash = hashlib.sha256(transform_json.encode("utf-8")).hexdigest()
                cursor.execute(
                    "INSERT INTO workmanship_sim_vm_poses "
                    "(gid,snapshot_gid,occurrence_gid,normalized_transform_json,pose_hash) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (pose_gid, snapshot_gid, occurrence_gid, transform_json, pose_hash),
                )

            if diff.removed_occurrence_gids:
                gids = tuple(_gid(value) for value in diff.removed_occurrence_gids)
                placeholders = ",".join("%s" for _ in gids)
                cursor.execute(
                    "UPDATE workmanship_sim_vm_occurrences SET status='removed',removed_at=NOW(6),"
                    "row_version=row_version+1,updated_at=NOW(6) "
                    "WHERE document_gid=%s AND tenant_gid=%s AND owner_gid=%s "
                    f"AND gid IN ({placeholders}) AND removed_at IS NULL",
                    (document_gid, tenant_gid, owner_gid, *gids),
                )

            if current_head_version == 0:
                cursor.execute(
                    "INSERT INTO workmanship_sim_vm_snapshot_heads "
                    "(document_gid,snapshot_gid,row_version) VALUES (%s,%s,1)",
                    (document_gid, snapshot_gid),
                )
                next_head_version = 1
            else:
                cursor.execute(
                    "UPDATE workmanship_sim_vm_snapshot_heads SET snapshot_gid=%s,"
                    "row_version=row_version+1,updated_at=NOW(6) "
                    "WHERE document_gid=%s AND row_version=%s",
                    (snapshot_gid, document_gid, current_head_version),
                )
                next_head_version = current_head_version + 1
            if cursor.rowcount != 1:
                raise VmRepositoryError("version_conflict")
        return {"snapshot_gid": snapshot_gid, "head_row_version": next_head_version}


repository = VmSnapshotRepository()

__all__ = ["VmRepositoryError", "VmSnapshotRepository", "repository"]
