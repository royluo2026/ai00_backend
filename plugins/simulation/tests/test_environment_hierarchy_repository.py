from __future__ import annotations

import pytest

from plugins.simulation.simulation_backend.data import workspace_repository as module
from plugins.simulation.simulation_backend.data.workspace_repository import WorkspaceRepository, WorkspaceRepositoryError
from plugins.simulation.tests.test_environment_document_repository import _install


def test_create_empty_alternate_hierarchy(monkeypatch):
    cursor = _install(monkeypatch, [{"row_version": 1}])
    result = WorkspaceRepository().create_alternate_hierarchy(
        workspace_gid="10", name="ALT Hier #1", source_bop_version_gid=None,
        expected_workspace_version=1, actor_gid="30", tenant_gid="20",
    )
    assert result == {"hierarchy_gid": "9001", "workspace_gid": "10", "name": "ALT Hier #1", "row_version": 1}
    assert any(sql.startswith("INSERT INTO workmanship_sim_workspace_hierarchies") for sql, _ in cursor.calls)


def test_create_hierarchy_rejects_foreign_or_missing_workspace(monkeypatch):
    _install(monkeypatch, [None])
    with pytest.raises(WorkspaceRepositoryError, match="workspace_not_found"):
        WorkspaceRepository().create_alternate_hierarchy(
            workspace_gid="10", name="ALT", source_bop_version_gid=None,
            expected_workspace_version=1, actor_gid="30", tenant_gid="20",
        )


def test_same_source_can_be_placed_more_than_once(monkeypatch):
    cursor = _install(monkeypatch, [
        {"row_version": 2, "workspace_gid": 10, "workspace_row_version": 4}, {"ok": 1}, {"position": 0},
        {"row_version": 3, "workspace_gid": 10, "workspace_row_version": 5}, {"ok": 1}, {"position": 1},
    ])
    repo = WorkspaceRepository()
    first = repo.add_placement(
        hierarchy_gid="12", target_node_gid="14", parent_placement_gid=None,
        source_kind="jt", source_ref={"document_gid": "44"}, transform=[1.0] * 16,
        expected_hierarchy_version=2, actor_gid="30", tenant_gid="20",
    )
    second = repo.add_placement(
        hierarchy_gid="12", target_node_gid="14", parent_placement_gid=None,
        source_kind="jt", source_ref={"document_gid": "44"}, transform=[1.0] * 16,
        expected_hierarchy_version=3, actor_gid="30", tenant_gid="20",
    )
    assert first["placement_gid"] == second["placement_gid"] == "9001"
    inserts = [sql for sql, _ in cursor.calls if sql.startswith("INSERT INTO workmanship_sim_workspace_placements")]
    assert len(inserts) == 2


def test_placement_rejects_target_outside_the_workspace(monkeypatch):
    cursor = _install(monkeypatch, [
        {"row_version": 2, "workspace_gid": 10, "workspace_row_version": 4}, None,
    ])
    with pytest.raises(WorkspaceRepositoryError, match="target_node_not_found"):
        WorkspaceRepository().add_placement(
            hierarchy_gid="12", target_node_gid="14", parent_placement_gid=None,
            source_kind="jt", source_ref={"document_gid": "44"}, transform=[1.0] * 16,
            expected_hierarchy_version=2, actor_gid="30", tenant_gid="20",
        )
    assert not any(sql.startswith("INSERT INTO workmanship_sim_workspace_placements") for sql, _ in cursor.calls)


def test_placement_rejects_parent_outside_the_hierarchy(monkeypatch):
    cursor = _install(monkeypatch, [
        {"row_version": 2, "workspace_gid": 10, "workspace_row_version": 4}, {"ok": 1}, None,
    ])
    with pytest.raises(WorkspaceRepositoryError, match="parent_placement_not_found"):
        WorkspaceRepository().add_placement(
            hierarchy_gid="12", target_node_gid="14", parent_placement_gid="15",
            source_kind="jt", source_ref={"document_gid": "44"}, transform=[1.0] * 16,
            expected_hierarchy_version=2, actor_gid="30", tenant_gid="20",
        )
    assert not any(sql.startswith("INSERT INTO workmanship_sim_workspace_placements") for sql, _ in cursor.calls)
