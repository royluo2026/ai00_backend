from plugins.simulation.simulation_backend.application.publish_plans import build_bop_publish_plan


NODES = [
    {"node_gid": "1", "parent_gid": None, "node_type": "line", "name": "L", "source_bop_node_gid": None, "position": 0},
    {"node_gid": "2", "parent_gid": "1", "node_type": "station", "name": "S", "source_bop_node_gid": None, "position": 0},
    {"node_gid": "3", "parent_gid": "2", "node_type": "process", "name": "P", "source_bop_node_gid": None, "position": 0},
    {"node_gid": "4", "parent_gid": "2", "node_type": "process", "name": "unselected", "source_bop_node_gid": None, "position": 1},
]


def _build(selected):
    return build_bop_publish_plan(
        environment_version_gid="90",
        environment_hash="a" * 64,
        base_bop_version_gid="80",
        base_bop_revision=7,
        base_bop_hash="b" * 64,
        nodes=NODES,
        bindings=[{"binding_gid": "11", "node_gid": "3", "occurrence_gid": "50", "role": "load"}],
        selected_node_gids=selected,
    )


def test_partial_selection_adds_parent_closure_and_excludes_unrelated_sibling():
    plan = _build(("3",))
    assert plan.selected_node_gids == ("3",)
    assert plan.parent_closure_gids == ("1", "2")
    assert [item["source_node_gid"] for item in plan.craft_preview_actions] == ["1", "2", "3"]
    assert "4" not in str(plan.craft_preview_actions)


def test_publish_uses_opaque_client_refs_and_preserves_load_role():
    plan = _build(("3",))
    process = plan.craft_preview_actions[-1]
    assert process["client_ref"] == "sim:90:3"
    assert process["parent_client_ref"] == "sim:90:2"
    assert plan.binding_actions == ({
        "client_ref": "sim-binding:90:11",
        "node_client_ref": "sim:90:3",
        "occurrence_gid": "50",
        "role": "load",
    },)


def test_publish_plan_hash_pins_bop_and_environment_inputs():
    first = _build(("3",))
    second = _build(("3",))
    assert first.plan_hash == second.plan_hash
    assert first.base_bop_revision == 7
    assert first.environment_hash == "a" * 64


def test_unknown_selection_is_rejected():
    try:
        _build(("999",))
    except ValueError as error:
        assert str(error) == "selected_node_not_found"
    else:
        raise AssertionError("unknown selection must fail")
