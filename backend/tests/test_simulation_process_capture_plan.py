from plugins.simulation.simulation_backend.domain.process_capture_plan import build_process_capture_plan


def test_forward_load_state_becomes_reverse_visibility_and_hides_only_at_load_boundary():
    plan = build_process_capture_plan(
        processes=[
            {"process_gid": "10", "station_order": 1, "process_order": 1, "operations": [
                {"operation_gid": "101", "parts": [{"occurrence_gid": "p1", "role": "load"}]},
            ]},
            {"process_gid": "20", "station_order": 1, "process_order": 2, "operations": [
                {"operation_gid": "201", "parts": [{"occurrence_gid": "p1", "role": "operate"}, {"occurrence_gid": "p2", "role": "load"}]},
            ]},
        ],
        initial_loaded_occurrence_gids=("body",),
        source_hashes={"environment": "a", "snapshot": "b", "bop": "c", "profile": "d"},
    )
    assert [step.process_gid for step in plan.steps] == ["20", "10"]
    assert plan.steps[0].visible_occurrence_gids == ("body", "p1", "p2")
    assert plan.steps[0].highlight_occurrence_gids == ("p1", "p2")
    assert plan.steps[0].hide_after_capture_occurrence_gids == ("p2",)
    assert plan.steps[1].visible_occurrence_gids == ("body", "p1")
    assert plan.steps[1].hide_after_capture_occurrence_gids == ("p1",)
    assert "body" not in plan.steps[1].hide_after_capture_occurrence_gids


def test_operations_are_aggregated_to_one_image_per_process_and_resources_do_not_accumulate():
    plan = build_process_capture_plan(
        processes=[{
            "process_gid": "10", "station_order": 1, "process_order": 1,
            "operations": [
                {"operation_gid": "101", "parts": [{"occurrence_gid": "p1", "role": "operate"}], "resources": ["tool-1"]},
                {"operation_gid": "102", "parts": [{"occurrence_gid": "p2", "role": "operate"}], "resources": ["fixture-1"]},
            ],
        }],
        initial_loaded_occurrence_gids=("p1", "p2"),
        source_hashes={"environment": "a", "snapshot": "b", "bop": "c", "profile": "d"},
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].operation_gids == ("101", "102")
    assert plan.steps[0].highlight_occurrence_gids == ("p1", "p2")
    assert plan.steps[0].resource_occurrence_gids == ("fixture-1", "tool-1")


def test_plan_order_and_hash_are_deterministic():
    kwargs = dict(
        processes=[
            {"process_gid": "20", "station_order": 2, "process_order": 1, "operations": []},
            {"process_gid": "10", "station_order": 1, "process_order": 9, "operations": []},
        ],
        initial_loaded_occurrence_gids=(),
        source_hashes={"environment": "a", "snapshot": "b", "bop": "c", "profile": "d"},
    )
    first = build_process_capture_plan(**kwargs)
    second = build_process_capture_plan(**kwargs)
    assert [step.process_gid for step in first.steps] == ["20", "10"]
    assert first.plan_hash == second.plan_hash
    assert first.algorithm_version == "process-capture.v1"


def test_duplicate_load_binding_is_rejected():
    processes = [
        {"process_gid": "10", "station_order": 1, "process_order": 1, "operations": [{"operation_gid": "1", "parts": [{"occurrence_gid": "p1", "role": "load"}]}]},
        {"process_gid": "20", "station_order": 1, "process_order": 2, "operations": [{"operation_gid": "2", "parts": [{"occurrence_gid": "p1", "role": "load"}]}]},
    ]
    try:
        build_process_capture_plan(processes=processes, initial_loaded_occurrence_gids=(), source_hashes={"environment": "a", "snapshot": "b", "bop": "c", "profile": "d"})
    except ValueError as error:
        assert str(error) == "duplicate_load_binding"
    else:
        raise AssertionError("duplicate load must fail")
