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
    assert result == {"hierarchy_gid": "9001", "root_node_gid": "9001", "workspace_gid": "10", "name": "ALT Hier #1", "row_version": 1}
    assert any(sql.startswith("INSERT INTO workmanship_sim_workspace_hierarchies") for sql, _ in cursor.calls)
    root_insert = next(call for call in cursor.calls if call[0].startswith("INSERT INTO workmanship_sim_workspace_nodes"))
    assert root_insert[1][4] == "9001"
    assert root_insert[1][5] is None
    assert root_insert[1][6:9] == ("alternate_hierarchy", "ALT Hier #1", 0)


def test_create_hierarchy_rejects_foreign_or_missing_workspace(monkeypatch):
    _install(monkeypatch, [None])
    with pytest.raises(WorkspaceRepositoryError, match="workspace_not_found"):
        WorkspaceRepository().create_alternate_hierarchy(
            workspace_gid="10", name="ALT", source_bop_version_gid=None,
            expected_workspace_version=1, actor_gid="30", tenant_gid="20",
        )


def test_get_alternate_hierarchy_returns_the_editable_node_tree_and_placements(monkeypatch):
    _install(monkeypatch, [
        {"hierarchy_gid": 12, "workspace_gid": 10, "name": "ALT", "status": "active",
         "projection_identity": "alt", "row_version": 2},
        [
            {"node_gid": 14, "workspace_gid": 10, "hierarchy_gid": 12, "parent_gid": None,
             "node_type": "line_process", "name": "总装线", "sort_order": 0,
             "source_bop_node_gid": 101, "row_version": 1},
        ],
        [],
    ])
    result = WorkspaceRepository().get_alternate_hierarchy(
        hierarchy_gid="12", tenant_gid="20", actor_gid="30",
    )
    assert result["nodes"] == [{
        "node_gid": "14", "workspace_gid": "10", "hierarchy_gid": "12", "parent_gid": None,
        "node_type": "line_process", "name": "总装线", "sort_order": 0,
        "source_bop_node_gid": "101", "row_version": 1,
    }]
    assert result["placements"] == []
    assert result["source_refs"] == {"model_references": [], "resource_references": []}


def test_insert_bop_projection_is_one_owned_workspace_transaction(monkeypatch):
    cursor = _install(monkeypatch, [
        {"row_version": 3, "cache_revision_hash": "sha256:" + "0" * 64, "status": "active"},
        None, None, {"position": 0},
    ])
    result = WorkspaceRepository().insert_bop_projection(
        workspace_gid="10", expected_workspace_version=3, actor_gid="30", tenant_gid="20",
        idempotency_key="bop-1", plan={
            "source_version_gid":"100", "source_content_hash":"sha256:"+"a"*64,
            "line_gid":"1", "fork_depth":"operation", "hierarchy_name":"L1",
            "plan_hash":"sha256:"+"b"*64, "nodes":[
                {"source_gid":"1","parent_source_gid":None,"node_type":"line_process","name":"L1","position":10},
                {"source_gid":"2","parent_source_gid":"1","node_type":"operation","name":"O1","position":20},
            ], "model_references":[{"source_node_gid":"2","reference":"part:9"}],
            "resource_references":[{"source_node_gid":"2","resource_type":"tool","reference":"tool:8"}],
        },
    )
    assert result["node_count"] == 2
    hierarchy_insert = next(call for call in cursor.calls if call[0].startswith("INSERT INTO workmanship_sim_workspace_hierarchies"))
    assert hierarchy_insert[1][5] == "100"
    assert hierarchy_insert[1][6] == "sha256:" + "a" * 64
    assert '"model_references"' in hierarchy_insert[1][7]
    assert len([call for call in cursor.calls if call[0].startswith("INSERT INTO workmanship_sim_workspace_nodes")]) == 2
    assert any(call[0].startswith("INSERT INTO workmanship_sim_workspace_idempotency") for call in cursor.calls)


def test_same_source_can_be_placed_more_than_once(monkeypatch):
    cursor = _install(monkeypatch, [
        {"row_version": 2, "workspace_gid": 10, "workspace_row_version": 4}, {"ok": 1},
        {"document_gid": 44, "artifact_ref_json": '{"artifact_id":"artifact-44","version":3}',
         "content_sha256": "b" * 64, "source_identity_hash": "a" * 64}, {"position": 0},
        {"row_version": 3, "workspace_gid": 10, "workspace_row_version": 5}, {"ok": 1},
        {"document_gid": 44, "artifact_ref_json": '{"artifact_id":"artifact-44","version":3}',
         "content_sha256": "b" * 64, "source_identity_hash": "a" * 64}, {"position": 1},
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


def test_placement_rejects_model_document_outside_the_workspace(monkeypatch):
    cursor = _install(monkeypatch, [
        {"row_version": 2, "workspace_gid": 10, "workspace_row_version": 4}, {"ok": 1}, None,
    ])
    with pytest.raises(WorkspaceRepositoryError, match="source_document_not_found"):
        WorkspaceRepository().add_placement(
            hierarchy_gid="12", target_node_gid="14", parent_placement_gid=None,
            source_kind="jt", source_ref={"document_gid": "44"}, transform=[1.0] * 16,
            expected_hierarchy_version=2, actor_gid="30", tenant_gid="20",
        )
    assert not any(sql.startswith("INSERT INTO workmanship_sim_workspace_placements") for sql, _ in cursor.calls)


def test_placement_persists_authoritative_model_document_evidence(monkeypatch):
    cursor = _install(monkeypatch, [
        {"row_version": 2, "workspace_gid": 10, "workspace_row_version": 4}, {"ok": 1},
        {"document_gid": 44, "artifact_ref_json": '{"artifact_id":"artifact-44","version":3}',
         "content_sha256": "b" * 64, "source_identity_hash": "a" * 64}, {"position": 0},
    ])
    WorkspaceRepository().add_placement(
        hierarchy_gid="12", target_node_gid="14", parent_placement_gid=None,
        source_kind="jt", source_ref={"document_gid": "44", "content_sha256": "sha256:" + "f" * 64},
        transform=[1.0] * 16, expected_hierarchy_version=2, actor_gid="30", tenant_gid="20",
    )
    insert = next(call for call in cursor.calls if call[0].startswith("INSERT INTO workmanship_sim_workspace_placements"))
    persisted = insert[1][8]
    assert persisted == '{"artifact_id":"artifact-44","artifact_version":"3","content_sha256":"sha256:' + "b" * 64 + '","document_gid":"44","source_identity_hash":"sha256:' + "a" * 64 + '"}'


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
        {"row_version": 2, "workspace_gid": 10, "workspace_row_version": 4}, {"ok": 1},
        {"document_gid": 44, "artifact_ref_json": '{"artifact_id":"artifact-44","version":3}',
         "content_sha256": "b" * 64, "source_identity_hash": "a" * 64}, None,
    ])
    with pytest.raises(WorkspaceRepositoryError, match="parent_placement_not_found"):
        WorkspaceRepository().add_placement(
            hierarchy_gid="12", target_node_gid="14", parent_placement_gid="15",
            source_kind="jt", source_ref={"document_gid": "44"}, transform=[1.0] * 16,
            expected_hierarchy_version=2, actor_gid="30", tenant_gid="20",
        )
    assert not any(sql.startswith("INSERT INTO workmanship_sim_workspace_placements") for sql, _ in cursor.calls)
