from __future__ import annotations

import pytest

from plugins.simulation.simulation_backend.domain.workspace import (
    SimulationWorkspace,
    WorkspaceConflict,
    WorkspaceRuleError,
)


def _workspace() -> SimulationWorkspace:
    gids = iter(("101", "102", "103", "104", "105", "106"))
    return SimulationWorkspace.create(
        gid="10", tenant_gid="20", owner_gid="30", name="my environment", gid_factory=gids.__next__
    )


def test_atomic_structure_changes_increment_cas_and_return_local_patch():
    workspace = _workspace()
    line = workspace.create_node(parent_gid=None, node_type="line", name="temp line", expected_row_version=1, idempotency_key="n1")
    station = workspace.create_node(parent_gid=line.entity_gid, node_type="station", name="station", expected_row_version=2, idempotency_key="n2")
    moved = workspace.move_node(node_gid=station.entity_gid, new_parent_gid=None, expected_row_version=3, idempotency_key="m1")
    assert moved.row_version == 4
    assert moved.patch == {"op": "move", "node_gid": "102", "parent_gid": None}


def test_same_idempotency_key_replays_and_conflicting_payload_is_rejected():
    workspace = _workspace()
    first = workspace.create_node(parent_gid=None, node_type="line", name="L", expected_row_version=1, idempotency_key="same")
    replay = workspace.create_node(parent_gid=None, node_type="line", name="L", expected_row_version=1, idempotency_key="same")
    assert replay == first
    with pytest.raises(WorkspaceConflict, match="idempotency_conflict"):
        workspace.create_node(parent_gid=None, node_type="line", name="different", expected_row_version=1, idempotency_key="same")


def test_cycle_and_stale_row_version_are_rejected():
    workspace = _workspace()
    line = workspace.create_node(parent_gid=None, node_type="line", name="L", expected_row_version=1, idempotency_key="1")
    station = workspace.create_node(parent_gid=line.entity_gid, node_type="station", name="S", expected_row_version=2, idempotency_key="2")
    with pytest.raises(WorkspaceRuleError, match="structure_cycle"):
        workspace.move_node(node_gid=line.entity_gid, new_parent_gid=station.entity_gid, expected_row_version=3, idempotency_key="3")
    with pytest.raises(WorkspaceConflict, match="version_conflict"):
        workspace.remove_node(node_gid=station.entity_gid, expected_row_version=2, idempotency_key="4")


def test_load_binding_is_unique_while_operate_bindings_can_repeat():
    workspace = _workspace()
    process = workspace.create_node(parent_gid=None, node_type="process", name="P1", expected_row_version=1, idempotency_key="1")
    operation = workspace.create_node(parent_gid=process.entity_gid, node_type="operation", name="O1", expected_row_version=2, idempotency_key="2")
    workspace.create_binding(node_gid=process.entity_gid, occurrence_gid="900", role="load", expected_row_version=3, idempotency_key="3")
    with pytest.raises(WorkspaceRuleError, match="load_binding_exists"):
        workspace.create_binding(node_gid=operation.entity_gid, occurrence_gid="900", role="load", expected_row_version=4, idempotency_key="4")
    operate = workspace.create_binding(node_gid=operation.entity_gid, occurrence_gid="900", role="operate", expected_row_version=4, idempotency_key="5")
    assert operate.patch["role"] == "operate"


def test_remove_node_soft_deletes_subtree_and_preserves_view_patch():
    workspace = _workspace()
    parent = workspace.create_node(parent_gid=None, node_type="line", name="L", expected_row_version=1, idempotency_key="1")
    child = workspace.create_node(parent_gid=parent.entity_gid, node_type="station", name="S", expected_row_version=2, idempotency_key="2")
    result = workspace.remove_node(node_gid=parent.entity_gid, expected_row_version=3, idempotency_key="3")
    assert set(result.patch["removed_node_gids"]) == {parent.entity_gid, child.entity_gid}
    assert workspace.nodes[parent.entity_gid].removed
    assert workspace.nodes[child.entity_gid].removed
