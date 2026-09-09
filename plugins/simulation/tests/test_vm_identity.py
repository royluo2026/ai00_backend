from __future__ import annotations

from plugins.simulation.simulation_backend.domain.vm_identity import (
    VmObservation,
    diff_snapshots,
)


def _gid_factory():
    values = iter(("9001", "9002", "9003", "9004"))
    return lambda: next(values)


def _part(**overrides) -> VmObservation:
    values = dict(
        occurrence_gid=None,
        source_instance_id="inst-1",
        session_gid="session-1",
        kind="part",
        model_number="W01-89184128",
        bom_line="W01-89184128/00;1",
        revision="00",
        catia_occurrence_name="bolt-left",
        normalized_transform=("1", "0", "0", "1"),
        removed=False,
    )
    values.update(overrides)
    return VmObservation(**values)


def _resource(**overrides) -> VmObservation:
    values = dict(
        occurrence_gid=None,
        source_instance_id="tool-inst-1",
        session_gid="session-1",
        kind="tool",
        model_number="TOOL-7",
        bom_line="TOOL-7/01;1",
        revision="01",
        catia_occurrence_name="tool-live-1",
        normalized_transform=("1", "0", "0", "1"),
        removed=False,
    )
    values.update(overrides)
    return VmObservation(**values)


def test_exact_part_and_moved_part_keep_gid_when_lineage_matches():
    previous = [_part(occurrence_gid="101")]
    exact = diff_snapshots(previous, [_part()], gid_factory=_gid_factory())
    moved = diff_snapshots(
        previous,
        [_part(source_instance_id="inst-new", normalized_transform=("1", "0", "9", "1"))],
        gid_factory=_gid_factory(),
    )
    assert exact.matches[0].occurrence_gid == "101"
    assert exact.matches[0].change == "unchanged"
    assert moved.matches[0].occurrence_gid == "101"
    assert moved.matches[0].change == "moved"


def test_same_bom_at_two_coordinates_is_two_part_instances():
    result = diff_snapshots(
        [],
        [_part(catia_occurrence_name="left"), _part(source_instance_id="inst-2", catia_occurrence_name="right", normalized_transform=("1", "0", "2", "1"))],
        gid_factory=_gid_factory(),
    )
    assert [item.occurrence_gid for item in result.matches] == ["9001", "9002"]


def test_resource_move_in_same_live_instance_keeps_gid_but_repeated_load_is_new():
    previous = [_resource(occurrence_gid="201")]
    moved = diff_snapshots(
        previous,
        [_resource(normalized_transform=("1", "0", "8", "1"))],
        gid_factory=_gid_factory(),
    )
    repeated = diff_snapshots(
        previous,
        [_resource(), _resource(source_instance_id="tool-inst-2", catia_occurrence_name="tool-live-2", normalized_transform=("1", "0", "8", "1"))],
        gid_factory=_gid_factory(),
    )
    assert moved.matches[0].occurrence_gid == "201"
    assert moved.matches[0].change == "moved"
    assert repeated.matches[1].occurrence_gid == "9001"
    assert repeated.matches[1].change == "added"


def test_deleted_then_reloaded_resource_gets_new_gid_with_predecessor():
    previous = [_resource(occurrence_gid="201", removed=True)]
    result = diff_snapshots(
        previous,
        [_resource(source_instance_id="tool-reload", catia_occurrence_name="tool-live-new")],
        gid_factory=_gid_factory(),
    )
    assert result.matches[0].occurrence_gid == "9001"
    assert result.matches[0].predecessor_gid == "201"
    assert result.matches[0].change == "reloaded"


def test_revision_upgrade_gets_new_gid_with_predecessor():
    previous = [_part(occurrence_gid="101")]
    result = diff_snapshots(
        previous,
        [_part(bom_line="W01-89184128/01;1", revision="01")],
        gid_factory=_gid_factory(),
    )
    assert result.matches[0].occurrence_gid == "9001"
    assert result.matches[0].predecessor_gid == "101"
    assert result.matches[0].change == "upgraded"


def test_ambiguous_part_lineage_does_not_guess():
    previous = [
        _part(occurrence_gid="101", source_instance_id="a", catia_occurrence_name=""),
        _part(occurrence_gid="102", source_instance_id="b", catia_occurrence_name="", normalized_transform=("1", "0", "2", "1")),
    ]
    result = diff_snapshots(
        previous,
        [_part(source_instance_id="new", catia_occurrence_name="", normalized_transform=("1", "0", "9", "1"))],
        gid_factory=_gid_factory(),
    )
    assert result.matches[0].change == "ambiguous"
    assert result.matches[0].occurrence_gid == "9001"
    assert set(result.matches[0].candidate_predecessor_gids) == {"101", "102"}
