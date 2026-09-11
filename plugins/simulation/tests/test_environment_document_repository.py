from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from plugins.simulation.simulation_backend.data import workspace_repository as module
from plugins.simulation.simulation_backend.data.workspace_repository import (
    WorkspaceRepository, WorkspaceRepositoryError, _dependency_source_identity,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.current = None
        self.calls = []
        self.rowcount = 1

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), tuple(params)))
        self.current = next(self.rows, None) if sql.lstrip().upper().startswith("SELECT") else None
        self.rowcount = 1
    def fetchone(self): return self.current


class _Connection:
    def __init__(self, cursor): self.value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.value


def _install(monkeypatch, rows):
    cursor = _Cursor(rows)
    monkeypatch.setattr(module, "get_simulation_conn", lambda: _Connection(cursor))
    monkeypatch.setattr(module, "next_gid", lambda: 9001)
    return cursor


def test_add_primary_model_document_is_atomic_and_invalidates_materialization(monkeypatch):
    cursor = _install(monkeypatch, [{"row_version": 3}, None])
    result = WorkspaceRepository().add_model_document(
        workspace_gid="10", expected_workspace_version=3,
        document={"role": "primary", "display_name": "W10", "media_type": "application/plmxml+xml",
                  "source_kind": "artifact", "source_identity_hash": "a" * 64,
                  "content_sha256": "b" * 64, "portability": "portable", "artifact_ref": {"artifact_id": "artifact_x"}},
        actor_gid="30", tenant_gid="20",
    )
    assert result["document_gid"] == "9001"
    insert = next(sql for sql, _ in cursor.calls if sql.startswith("INSERT INTO workmanship_sim_vm_documents"))
    assert "primary_slot" in insert
    assert any("workmanship_sim_materialization_verifications" in sql and "stale" in sql for sql, _ in cursor.calls)


def test_add_second_primary_is_rejected_before_insert(monkeypatch):
    cursor = _install(monkeypatch, [{"row_version": 3}, {"gid": 44}])
    with pytest.raises(WorkspaceRepositoryError, match="primary_model_document_exists"):
        WorkspaceRepository().add_model_document(
            workspace_gid="10", expected_workspace_version=3,
            document={"role": "primary", "display_name": "W10", "media_type": "application/plmxml+xml",
                      "source_kind": "artifact", "source_identity_hash": "a" * 64,
                      "content_sha256": "b" * 64, "portability": "portable", "artifact_ref": {"artifact_id": "artifact_x"}},
            actor_gid="30", tenant_gid="20",
        )
    assert not any(sql.startswith("INSERT INTO workmanship_sim_vm_documents") for sql, _ in cursor.calls)


def test_add_document_rejects_stale_workspace_version(monkeypatch):
    cursor = _install(monkeypatch, [{"row_version": 4}])
    with pytest.raises(WorkspaceRepositoryError, match="version_conflict"):
        WorkspaceRepository().add_model_document(
            workspace_gid="10", expected_workspace_version=3,
            document={"role": "inserted", "display_name": "tool", "media_type": "model/vnd.jt",
                      "source_kind": "artifact", "source_identity_hash": "a" * 64,
                      "content_sha256": "b" * 64, "portability": "portable", "artifact_ref": {"artifact_id": "artifact_x"}},
            actor_gid="30", tenant_gid="20",
        )
    assert not any(sql.startswith("INSERT") for sql, _ in cursor.calls)


def test_migration_declares_document_hierarchy_placement_and_verification_storage():
    migration = (Path(__file__).resolve().parents[3] / "backend/db/migrations/domains/simulation/0018_simulation_environment_documents_and_hierarchies.sql").read_text(encoding="utf-8")
    for name in ("primary_slot", "workmanship_sim_workspace_hierarchies", "workmanship_sim_workspace_placements",
                 "workmanship_sim_vm_session_documents", "workmanship_sim_materialization_verifications"):
        assert name in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS `uq_sim_vm_document_primary`" in migration


def test_runtime_projection_migration_binds_exact_connector_plan():
    migration = (Path(__file__).resolve().parents[3] / "backend/db/migrations/domains/simulation/0019_simulation_runtime_package_projection.sql").read_text(encoding="utf-8")
    assert "workmanship_sim_runtime_package_projections" in migration
    assert "connector_plan_id" in migration
    assert "uq_sim_runtime_package_plan" in migration


def test_runtime_outcome_records_tree_readback_but_not_semantic_verification(monkeypatch):
    cursor = _install(monkeypatch, [{
        "gid": 9001, "workspace_gid": 10, "version_gid": 11, "manifest_hash": "a" * 64,
    }])
    result = WorkspaceRepository().apply_runtime_package_outcome(
        connector_plan_id="runtime-plan-1",
        plan=SimpleNamespace(plan_id="runtime-plan-1", capability_id="simulation.environment.runtime_package.open.request"),
        outcome=SimpleNamespace(overall_status="succeeded", steps=[
            SimpleNamespace(step_id="step-00001", status="succeeded", result={"opened": True}),
            SimpleNamespace(step_id="step-00002", status="succeeded", result={"nodes": [], "cache_state": "verified"}),
        ]),
        tenant_gid="20", actor_gid="30",
    )
    assert result["state"] == "read_back"
    update = next((sql, params) for sql, params in cursor.calls if sql.startswith("UPDATE workmanship_sim_runtime_package_projections"))
    assert update[1][0] == "read_back"
    assert '"semantic_verification":"pending"' in update[1][1]


def test_runtime_package_projection_accepts_shared_frozen_version(monkeypatch):
    cursor = _install(monkeypatch, [{"present": 1}])
    result = WorkspaceRepository().save_runtime_package_projection(
        workspace_gid="10", version_gid="11", connector_plan_id="runtime-plan-1",
        manifest_hash="sha256:" + "a" * 64,
        runtime_package_artifact_ref={"artifact_id": "root"}, connector_device_id="device-1",
        report={"semantic_verification": "pending"}, tenant_gid="20", actor_gid="30",
    )
    assert result["state"] == "pending"
    visibility_query = next(sql for sql, _ in cursor.calls if sql.startswith("SELECT 1 FROM workmanship_sim_workspace_versions"))
    assert "w.owner_gid=%s OR w.visibility='shared'" in visibility_query
    assert any(sql.startswith("INSERT INTO workmanship_sim_runtime_package_projections") for sql, _ in cursor.calls)


def test_runtime_package_projection_replays_the_same_connector_plan(monkeypatch):
    artifact = {"artifact_id": "new-root", "sha256": "c" * 64, "byte_size": 42, "media_type": "application/plmxml+xml"}
    cursor = _install(monkeypatch, [{"present": 1}, {
        "gid": 99, "workspace_gid": 10, "version_gid": 11, "tenant_gid": 20, "actor_gid": 30,
        "state": "pending", "manifest_hash": "a" * 64,
        "runtime_package_artifact_ref_json": {**artifact, "artifact_id": "old-root"}, "connector_device_id": "device-1",
    }])
    result = WorkspaceRepository().save_runtime_package_projection(
        workspace_gid="10", version_gid="11", connector_plan_id="runtime-plan-1",
        manifest_hash="sha256:" + "a" * 64, runtime_package_artifact_ref=artifact,
        connector_device_id="device-1", report={}, tenant_gid="20", actor_gid="30",
    )
    assert result["projection_gid"] == "99"
    assert not any(sql.startswith("INSERT INTO workmanship_sim_runtime_package_projections") for sql, _ in cursor.calls)


def test_dependency_identity_is_namespaced_by_parent_document_content():
    first = _dependency_source_identity("a" * 64, "../parts/door.jt")
    second = _dependency_source_identity("b" * 64, "../parts/door.jt")
    assert first != second
    assert first == _dependency_source_identity("a" * 64, "..\\PARTS\\DOOR.JT")
