"""Authoritative, archive-only persistence for governed VM checkpoints."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from backend.platform_sdk.ids import next_gid

from .connection import get_simulation_conn


class VmCheckpointRepositoryError(RuntimeError):
    pass


def _gid(value, field: str) -> str:
    text = str(value or "")
    if not text.isdecimal() or int(text) <= 0:
        raise VmCheckpointRepositoryError(f"{field}_invalid")
    return text


def _project(row):
    value = dict(row)
    for field in ("gid", "snapshot_gid", "workspace_gid", "created_by"):
        if value.get(field) is not None:
            value["checkpoint_gid" if field == "gid" else field] = str(value.pop(field) if field == "gid" else value[field])
    for field in ("created_at", "archived_at"):
        if value.get(field) is not None and not isinstance(value[field], str):
            value[field] = value[field].isoformat()
    value["row_version"] = int(value["row_version"])
    return value


class VmCheckpointRepository:
    def __init__(self, connection_factory: Callable = get_simulation_conn, *, gid_factory=next_gid):
        self._connection_factory = connection_factory
        self._gid_factory = gid_factory

    def create_from_request(self, *, snapshot_request_id: str, snapshot_hash: str, workspace_gid: str,
                            tenant_gid: str, created_by: str, scope: str, name: str, note: str,
                            idempotency_key: str):
        workspace_gid, tenant_gid, created_by = (_gid(workspace_gid, "workspace_gid"),
                                                  _gid(tenant_gid, "tenant_gid"), _gid(created_by, "created_by"))
        request_hash = hashlib.sha256(json.dumps({"snapshot_request_id": snapshot_request_id,
            "snapshot_hash": snapshot_hash, "scope": scope, "name": name, "note": note},
            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        raw_hash = snapshot_hash.removeprefix("sha256:")
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT status,snapshot_hash FROM workmanship_sim_document_snapshot_requests "
                "WHERE snapshot_request_id=%s AND (owner_gid=%s OR team_gid=%s) FOR UPDATE",
                (snapshot_request_id, created_by, tenant_gid),
            )
            request = cursor.fetchone()
            if not request:
                raise VmCheckpointRepositoryError("document_snapshot_not_found")
            if request["status"] != "completed":
                raise VmCheckpointRepositoryError("document_snapshot_not_completed")
            if request["snapshot_hash"] != snapshot_hash:
                raise VmCheckpointRepositoryError("snapshot_hash_mismatch")
            cursor.execute(
                "SELECT s.gid snapshot_gid FROM workmanship_sim_vm_snapshots s "
                "JOIN workmanship_sim_vm_documents d ON d.gid=s.document_gid "
                "WHERE d.workspace_gid=%s AND d.removed_at IS NULL AND s.removed_at IS NULL "
                "AND s.snapshot_hash=%s ORDER BY s.created_at DESC LIMIT 1 FOR UPDATE",
                (workspace_gid, raw_hash),
            )
            snapshot = cursor.fetchone()
            if not snapshot:
                raise VmCheckpointRepositoryError("vm_snapshot_projection_required")
            cursor.execute(
                "SELECT gid,snapshot_gid,workspace_gid,created_by,scope,name,note,row_version,created_at,archived_at,request_hash "
                "FROM workmanship_sim_vm_checkpoints WHERE workspace_gid=%s AND created_by=%s AND idempotency_key=%s FOR UPDATE",
                (workspace_gid, created_by, idempotency_key),
            )
            current = cursor.fetchone()
            if current:
                if current.pop("request_hash") != request_hash:
                    raise VmCheckpointRepositoryError("idempotency_conflict")
                return _project(current)
            checkpoint_gid = _gid(self._gid_factory(), "checkpoint_gid")
            cursor.execute(
                "INSERT INTO workmanship_sim_vm_checkpoints "
                "(gid,snapshot_gid,workspace_gid,tenant_gid,created_by,scope,name,note,idempotency_key,request_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (checkpoint_gid, snapshot["snapshot_gid"], workspace_gid, tenant_gid, created_by,
                 scope, name, note or None, idempotency_key, request_hash),
            )
            cursor.execute(
                "SELECT gid,snapshot_gid,workspace_gid,created_by,scope,name,note,row_version,created_at,archived_at "
                "FROM workmanship_sim_vm_checkpoints WHERE gid=%s", (checkpoint_gid,),
            )
            return _project(cursor.fetchone())

    def search(self, *, workspace_gid: str, tenant_gid: str, created_by: str, offset: int, page_size: int,
               include_archived: bool = False):
        clauses = "" if include_archived else " AND archived_at IS NULL"
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT gid,snapshot_gid,workspace_gid,created_by,scope,name,note,row_version,created_at,archived_at "
                "FROM workmanship_sim_vm_checkpoints WHERE workspace_gid=%s AND tenant_gid=%s "
                "AND (created_by=%s OR scope='shared_baseline')" + clauses +
                " ORDER BY created_at DESC,gid DESC LIMIT %s OFFSET %s",
                (_gid(workspace_gid, "workspace_gid"), _gid(tenant_gid, "tenant_gid"),
                 _gid(created_by, "created_by"), page_size + 1, offset),
            )
            rows = list(cursor.fetchall())
        more = len(rows) > page_size
        return {"items": [_project(row) for row in rows[:page_size]],
                "next_cursor": str(offset + page_size) if more else None}

    def archive(self, *, checkpoint_gid: str, workspace_gid: str, tenant_gid: str, created_by: str,
                expected_row_version: int, allow_shared: bool, idempotency_key: str):
        del idempotency_key  # row-version makes repeated archive deterministic.
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_vm_checkpoints SET archived_at=COALESCE(archived_at,NOW(6)),"
                "row_version=IF(archived_at IS NULL,row_version+1,row_version) WHERE gid=%s AND workspace_gid=%s "
                "AND tenant_gid=%s AND row_version=%s AND (created_by=%s OR %s=1)",
                (_gid(checkpoint_gid, "checkpoint_gid"), _gid(workspace_gid, "workspace_gid"),
                 _gid(tenant_gid, "tenant_gid"), expected_row_version, _gid(created_by, "created_by"), int(allow_shared)),
            )
            if cursor.rowcount != 1:
                raise VmCheckpointRepositoryError("vm_checkpoint_not_found_or_conflict")
            cursor.execute(
                "SELECT gid,snapshot_gid,workspace_gid,created_by,scope,name,note,row_version,created_at,archived_at "
                "FROM workmanship_sim_vm_checkpoints WHERE gid=%s", (checkpoint_gid,),
            )
            return _project(cursor.fetchone())

    def can_read(self, checkpoint_gid: str, *, tenant_gid: str, created_by: str) -> bool:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_vm_checkpoints WHERE gid=%s AND tenant_gid=%s "
                "AND (created_by=%s OR scope='shared_baseline') LIMIT 1",
                (_gid(checkpoint_gid, "checkpoint_gid"), _gid(tenant_gid, "tenant_gid"), _gid(created_by, "created_by")),
            )
            return cursor.fetchone() is not None


repository = VmCheckpointRepository()

__all__ = ["VmCheckpointRepository", "VmCheckpointRepositoryError", "repository"]
