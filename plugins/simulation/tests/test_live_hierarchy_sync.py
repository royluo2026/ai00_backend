"""The merge must not erase manual edits or mistake partial reads for deletion."""
import pytest
from dataclasses import replace

from plugins.simulation.simulation_backend.domain.live_hierarchy_sync import (
    HierarchyNode, HierarchySnapshot, SyncValidationError, reconcile,
)


def node(key, parent=None, name=None, source=None):
    return HierarchyNode(key, parent, name or key, source)


def snap(nodes, **changes):
    values = dict(environment_id="env-a", document_session="session-a", complete=True, nodes=tuple(nodes))
    values.update(changes)
    return HierarchySnapshot(**values)


def test_manual_reference_is_returned_without_changing_source_identity():
    root = node("root")
    reference = HierarchyNode("ref", "root", "lamp", "artifact:abc",
                              insertion_instance_id="insertion-a", occurrence_id="lamp-1")
    result = reconcile(snap([root]), snap([root]), snap([root, reference]))
    assert result.conflicts == ()
    assert result.nodes == (reference, root)


def test_disjoint_edits_merge_but_same_node_edits_conflict():
    base = snap([node("a"), node("b")])
    result = reconcile(base, snap([node("a", name="AI00"), node("b")]),
                       snap([node("a"), node("b", name="manual")]))
    assert result.nodes == (node("a", name="AI00"), node("b", name="manual"))
    conflict = reconcile(base, snap([node("a", name="AI00"), node("b")]),
                         snap([node("a", name="manual"), node("b")]))
    assert conflict.nodes is None
    assert [(c.node_id, c.reason) for c in conflict.conflicts] == [("a", "concurrent_change")]


def test_delete_parent_against_new_manual_child_is_conflict():
    result = reconcile(snap([node("root")]), snap([]), snap([node("root"), node("child", "root")]))
    assert result.nodes is None
    assert any(c.reason == "parent_deleted" for c in result.conflicts)


def test_identical_deletion_and_identical_creation_are_idempotent():
    root = node("root")
    assert reconcile(snap([root]), snap([]), snap([])).nodes == ()
    assert reconcile(snap([]), snap([root]), snap([root])).nodes == (root,)


@pytest.mark.parametrize("changes", [dict(complete=False), dict(environment_id="env-b"), dict(document_session="session-b")])
def test_incomplete_or_wrong_session_observation_never_means_delete(changes):
    base = snap([node("root")])
    with pytest.raises(SyncValidationError):
        reconcile(base, base, snap([], **changes))


@pytest.mark.parametrize("nodes", [[node("a"), node("a")], [node("a", "missing")],
                                    [node("a", "b"), node("b", "a")]])
def test_invalid_forests_rejected(nodes):
    with pytest.raises(SyncValidationError):
        reconcile(snap([]), snap(nodes), snap([]))


def test_disjoint_moves_that_jointly_create_cycle_are_conflict():
    base = snap([node("a"), node("b")])
    result = reconcile(base, snap([node("a", "b"), node("b")]), snap([node("a"), node("b", "a")]))
    assert result.nodes is None
    assert any(c.reason == "merged_cycle" for c in result.conflicts)


def test_ten_thousand_deep_nodes_do_not_recurse_or_mutate_input():
    values = tuple(node(str(i), str(i-1) if i else None) for i in range(10000))
    base = snap(values)
    changed = snap((*values[:-1], node("9999", "9998", "renamed")))
    result = reconcile(base, base, changed)
    assert len(result.nodes) == 10000
    assert next(n for n in result.nodes if n.node_id == "9999").name == "renamed"
    assert base.nodes[-1].name == "9999"


def test_source_only_reference_is_rejected_as_ambiguous():
    reference = node("ref", source="same-file.plmxml")
    with pytest.raises(SyncValidationError, match="hierarchy_reference_incomplete"):
        reconcile(snap([]), snap([reference]), snap([]))


def test_same_source_and_occurrence_in_two_insertions_are_distinct():
    first = HierarchyNode("ref-a", None, "lamp", "same-file.plmxml",
                          insertion_instance_id="insertion-a", occurrence_id="lamp-1")
    second = replace(first, node_id="ref-b", insertion_instance_id="insertion-b")
    result = reconcile(snap([]), snap([first]), snap([second]))
    assert result.nodes == (first, second)


def test_retargeting_to_different_insertions_is_a_real_conflict():
    first = HierarchyNode("ref", None, "lamp", "same-file.plmxml",
                          insertion_instance_id="insertion-a", occurrence_id="lamp-1")
    local = replace(first, insertion_instance_id="insertion-b")
    remote = replace(first, insertion_instance_id="insertion-c")
    result = reconcile(snap([first]), snap([local]), snap([remote]))
    assert result.nodes is None
    assert result.conflicts[0].reason == "concurrent_change"


@pytest.mark.parametrize("field", ["source_identity", "insertion_instance_id", "occurrence_id"])
def test_partial_reference_identity_is_not_accepted(field):
    reference = HierarchyNode("ref", None, "lamp", "same-file.plmxml",
                              insertion_instance_id="insertion-a", occurrence_id="lamp-1")
    with pytest.raises(SyncValidationError, match="hierarchy_reference_incomplete"):
        reconcile(snap([]), snap([replace(reference, **{field: None})]), snap([]))


def test_one_hundred_thousand_siblings_preserve_independent_changes():
    root = node("root")
    values = (root, *(node(f"leaf-{i}", "root") for i in range(100_000)))
    base = snap(values)
    local = snap((root, replace(values[1], name="local"), *values[2:]))
    remote = snap((*values[:-1], replace(values[-1], name="remote")))
    result = reconcile(base, local, remote)
    assert not result.conflicts
    assert len(result.nodes) == 100_001
    mapped = {n.node_id: n for n in result.nodes}
    assert mapped["leaf-0"].name == "local"
    assert mapped["leaf-99999"].name == "remote"
