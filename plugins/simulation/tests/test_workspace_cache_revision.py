from __future__ import annotations

from pathlib import Path

import pytest

from plugins.simulation.simulation_backend.data import workspace_repository as module
from plugins.simulation.simulation_backend.data.workspace_repository import (
    WorkspaceRepository,
    WorkspaceRepositoryError,
    next_cache_revision_hash,
)


class _Cursor:
    def __init__(self, row_version: int = 1):
        self.row_version = row_version
        self.calls: list[tuple[str, tuple]] = []
        self.rowcount = 1
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, tuple(params)))
        self.rowcount = 1
        if normalized.startswith("SELECT row_version,status,tenant_gid"):
            self.current = {
                "row_version": self.row_version,
                "status": "active",
                "tenant_gid": 20,
                "cache_revision_hash": "sha256:" + "0" * 64,
            }
        elif normalized.startswith("SELECT request_hash,response_json"):
            self.current = None
        elif "COALESCE(MAX(sort_order)" in normalized:
            self.current = {"position": 0}
        else:
            self.current = None

    def fetchone(self):
        return self.current


class _Connection:
    def __init__(self, cursor: _Cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value


def test_cache_revision_hash_is_deterministic_and_version_sensitive():
    patch = {"op": "create", "node_gid": "41", "name": "Line 1"}

    first = next_cache_revision_hash("sha256:" + "0" * 64, patch, 2)
    reordered = next_cache_revision_hash(
        "sha256:" + "0" * 64,
        {"name": "Line 1", "node_gid": "41", "op": "create"},
        2,
    )
    next_version = next_cache_revision_hash("sha256:" + "0" * 64, patch, 3)

    assert first == reordered
    assert first != next_version
    assert first.startswith("sha256:") and len(first) == 71


def test_workspace_mutation_advances_row_version_and_cache_hash_in_one_update(monkeypatch):
    cursor = _Cursor(row_version=1)
    monkeypatch.setattr(module, "get_simulation_conn", lambda: _Connection(cursor))

    result = WorkspaceRepository().mutate(
        workspace_gid="10",
        tenant_gid="20",
        owner_gid="30",
        expected_row_version=1,
        idempotency_key="create-node-1",
        operation="create_node",
        values={"parent_gid": None, "node_type": "line", "name": "Line 1"},
    )

    update_sql, update_params = next(
        call for call in cursor.calls
        if call[0].startswith("UPDATE workmanship_sim_workspaces SET")
    )
    assert "cache_revision_hash=%s,row_version=%s" in update_sql
    assert result["cache_revision_hash"] == update_params[0]
    assert result["row_version"] == update_params[1] == 2


def test_version_conflict_updates_neither_row_version_nor_cache_hash(monkeypatch):
    cursor = _Cursor(row_version=2)
    monkeypatch.setattr(module, "get_simulation_conn", lambda: _Connection(cursor))

    with pytest.raises(WorkspaceRepositoryError, match="version_conflict"):
        WorkspaceRepository().mutate(
            workspace_gid="10",
            tenant_gid="20",
            owner_gid="30",
            expected_row_version=1,
            idempotency_key="create-node-1",
            operation="create_node",
            values={"parent_gid": None, "node_type": "line", "name": "Line 1"},
        )

    assert not any(
        sql.startswith("UPDATE workmanship_sim_workspaces SET") for sql, _ in cursor.calls
    )


def test_migration_adds_cache_revision_and_declares_checkpoint_and_diff_tables():
    migration = (
        Path(__file__).resolve().parents[3]
        / "backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql"
    ).read_text(encoding="utf-8")

    assert "cache_revision_hash" in migration
    assert "workmanship_sim_vm_checkpoints" in migration
    assert "workmanship_sim_vm_diff_reports" in migration
    assert "workmanship_sim_vm_diff_items" in migration


def test_every_workspace_write_path_persists_cache_revision_hash():
    source = Path(
        "plugins/simulation/simulation_backend/data/workspace_repository.py"
    ).read_text(encoding="utf-8")
    assert source.count("INSERT INTO workmanship_sim_workspaces") == 3
    assert source.count("primary_project_gid,cache_revision_hash,row_version)") == 3
    assert "SET removed_at=NOW(6),cache_revision_hash=%s,row_version=%s" in source
    assert "SET cache_revision_hash=%s,row_version=%s,updated_at=NOW(6)" in source
    assert "SET cache_revision_hash=%s,row_version=%s,updated_at=NOW(6) WHERE gid=%s" in source
