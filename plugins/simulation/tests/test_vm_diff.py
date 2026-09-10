from plugins.simulation.simulation_backend.domain.vm_diff import compare_vm_snapshots
from plugins.simulation.simulation_backend.domain.vm_identity import VmObservation


def observation(gid, *, source=None, parent=(), order=0, revision="A", representation=("a.jt",),
                geometry="g1", name=None, attributes=(), transform=("0",)):
    return VmObservation(occurrence_gid=gid, source_instance_id=source or f"src-{gid}", session_gid="1",
        kind="part", model_number=f"P-{gid}", bom_line=f"L-{gid}", revision=revision,
        catia_occurrence_name=name or f"node-{gid}", normalized_transform=transform,
        parent_path=parent, representation_locations=representation, order_index=order,
        geometry_hash=geometry, attributes=attributes)


def test_diff_classifies_each_atomic_change_in_stable_order():
    before = [
        observation("1"), observation("2", revision="A"), observation("3", representation=("old.jt",)),
        observation("4", geometry="old"), observation("5", parent=("old",)), observation("6", order=1),
        observation("7", name="old"), observation("8", attributes=(("color", "red"),)), observation("9"),
    ]
    after = [
        observation("1"), observation("2", revision="B"), observation("3", representation=("new.jt",)),
        observation("4", geometry="new"), observation("5", parent=("new",)), observation("6", order=2),
        observation("7", name="new"), observation("8", attributes=(("color", "blue"),)), observation("10"),
    ]
    result = compare_vm_snapshots(before, after, algorithm_version="vm-diff-v1")
    assert [item.change_type for item in result.items] == [
        "revision_upgraded", "representation_replaced", "geometry_content_changed", "moved",
        "reordered", "renamed", "attributes_changed", "removed", "added",
    ]
    assert result.summary == {change: 1 for change in [
        "added", "attributes_changed", "geometry_content_changed", "moved", "removed", "renamed",
        "reordered", "representation_replaced", "revision_upgraded",
    ]}


def test_one_node_can_emit_multiple_atomic_changes():
    result = compare_vm_snapshots(
        [observation("1", revision="A", geometry="old")],
        [observation("1", revision="B", geometry="new")], algorithm_version="vm-diff-v1")
    assert [item.change_type for item in result.items] == ["revision_upgraded", "geometry_content_changed"]


def test_ambiguous_identity_is_reported_instead_of_guessed():
    before = [observation("1", source="same"), observation("2", source="same")]
    after = [observation(None, source="same")]
    result = compare_vm_snapshots(before, after, algorithm_version="vm-diff-v1")
    assert result.items[0].change_type == "ambiguous_identity"
    assert result.items[0].payload["candidate_occurrence_gids"] == ["1", "2"]


def test_diff_order_is_deterministic_for_unordered_inputs():
    forward = compare_vm_snapshots([observation("2"), observation("1")], [observation("4"), observation("3")], algorithm_version="v1")
    reverse = compare_vm_snapshots([observation("1"), observation("2")], [observation("3"), observation("4")], algorithm_version="v1")
    assert forward == reverse
