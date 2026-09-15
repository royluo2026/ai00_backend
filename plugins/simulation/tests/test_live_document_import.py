"""Live model observations preserve insertion identity, never infer history."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from plugins.simulation.simulation_backend.domain.live_document_import import (
    ModelObservation, project_model_insertions,
)


NOW = datetime(2026, 9, 14, 10, tzinfo=timezone.utc)


def model(key="native-a", **changes):
    values = dict(native_instance_id=key, source_kind="local_file",
                  source_identity="file:same.plmxml", display_name="Same model",
                  content_fingerprint=None, inserted_at=None)
    values.update(changes)
    return ModelObservation(**values)


def project(models, **changes):
    values = dict(document_session="session-a", observed_at=NOW,
                  models=tuple(models), complete=True)
    values.update(changes)
    return project_model_insertions(**values)


def test_repeated_same_source_creates_distinct_instances():
    result = project([model(), model("native-b")])
    assert len(result.instances) == 2
    assert len({row.insertion_instance_id for row in result.instances}) == 2
    assert len({row.source_identity for row in result.instances}) == 1


def test_manual_existing_model_has_first_seen_time_not_invented_insertion_time():
    row = project([model()]).instances[0]
    assert row.first_seen_at == NOW
    assert row.inserted_at is None


def test_repeat_read_preserves_identity_and_first_seen_but_updates_observation():
    initial = project([model()])
    later = project([model(content_fingerprint="sha256:" + "a" * 64)],
                    observed_at=NOW + timedelta(hours=1), previous=initial)
    assert later.instances[0].insertion_instance_id == initial.instances[0].insertion_instance_id
    assert later.instances[0].first_seen_at == NOW
    assert later.observed_at == NOW + timedelta(hours=1)
    assert later.instances[0].content_fingerprint == "sha256:" + "a" * 64


def test_partial_read_preserves_unobserved_instances_and_marks_them_pending():
    initial = project([model(), model("native-b")])
    later = project([model()], previous=initial, complete=False)
    assert later.complete is False
    assert len(later.instances) == 2
    assert later.unobserved_instance_ids == (initial.instances[1].insertion_instance_id,)


def test_complete_read_still_does_not_delete_instances_implicitly():
    initial = project([model()])
    result = project([], previous=initial)
    assert result.instances == initial.instances
    assert result.unobserved_instance_ids == (initial.instances[0].insertion_instance_id,)


def test_online_and_local_models_with_same_name_remain_separate():
    result = project([model(), model("native-b", source_kind="online", source_identity="tc:part:A")])
    assert {row.source_kind for row in result.instances} == {"local_file", "online"}


def test_insert_time_from_native_evidence_is_retained_when_later_read_omits_it():
    inserted = NOW - timedelta(days=1)
    initial = project([model(inserted_at=inserted)])
    later = project([model()], previous=initial)
    assert later.instances[0].inserted_at == inserted


@pytest.mark.parametrize("changes,error", [
    ({"document_session": "session-b"}, "document_session_changed"),
    ({"observed_at": NOW - timedelta(seconds=1)}, "observation_time_regressed"),
])
def test_stale_or_other_session_rejected(changes, error):
    with pytest.raises(ValueError, match=error):
        project([model()], previous=project([model()]), **changes)


def test_duplicate_native_identity_rejected_even_if_content_matches():
    with pytest.raises(ValueError, match="model_instance_duplicate"):
        project([model(), model()])


def test_reused_native_identity_with_different_source_is_not_silently_rebound():
    with pytest.raises(ValueError, match="model_instance_identity_changed"):
        project([model(source_identity="another-file")], previous=project([model()]))


@pytest.mark.parametrize("timestamp", [NOW.replace(tzinfo=None), NOW + timedelta(days=1)])
def test_invalid_or_future_insertion_time_rejected(timestamp):
    with pytest.raises(ValueError, match="model_inserted_at_invalid"):
        project([model(inserted_at=timestamp)])


def test_disappeared_then_reappeared_native_key_requires_reconciliation():
    initial = project([model()])
    absent = project([], previous=initial)
    with pytest.raises(ValueError, match="model_instance_reappeared"):
        project([model()], previous=absent)


def test_partial_read_does_not_erase_previous_evidence_of_disappearance():
    initial = project([model()])
    absent = project([], previous=initial)
    partial = project([], previous=absent, complete=False)
    with pytest.raises(ValueError, match="model_instance_reappeared"):
        project([model()], previous=partial)


def test_partial_read_then_reappearance_is_not_a_new_insertion():
    initial = project([model()])
    partial = project([], previous=initial, complete=False)
    restored = project([model()], previous=partial)
    assert restored.instances[0].insertion_instance_id == initial.instances[0].insertion_instance_id


def test_changed_native_insertion_time_cannot_reuse_old_instance():
    initial = project([model(inserted_at=NOW - timedelta(days=1))])
    with pytest.raises(ValueError, match="model_instance_identity_changed"):
        project([model(inserted_at=NOW)], previous=initial)


def test_ah_links_resolve_two_identical_sources_to_distinct_instances():
    from plugins.simulation.simulation_backend.domain.live_document_import import (
        NativeProductReference, project_hierarchy_references,
    )
    from plugins.simulation.simulation_backend.domain.live_hierarchy_sync import HierarchyNode
    models = project([model(), model("native-b")])
    nodes = (HierarchyNode("root", None, "AH"), HierarchyNode("a", "root", "lamp"),
             HierarchyNode("b", "root", "lamp"))
    references = (NativeProductReference("a", "native-a", "lamp-1"),
                  NativeProductReference("b", "native-b", "lamp-1"))
    result = project_hierarchy_references(document_session="session-a", nodes=nodes,
                                         references=references, models=models, complete=True)
    assert result.complete is True
    assert result.unresolved_references == ()
    assert result.nodes[1].insertion_instance_id == models.instances[0].insertion_instance_id
    assert result.nodes[2].insertion_instance_id == models.instances[1].insertion_instance_id
    assert result.nodes[1].occurrence_id == result.nodes[2].occurrence_id == "lamp-1"
    assert nodes[1].source_identity is None  # input is not rewritten


def test_unresolved_ah_reference_is_preserved_and_prevents_complete_baseline():
    from plugins.simulation.simulation_backend.domain.live_document_import import (
        NativeProductReference, project_hierarchy_references,
    )
    from plugins.simulation.simulation_backend.domain.live_hierarchy_sync import HierarchyNode
    reference = NativeProductReference("a", "unknown-model", "lamp-1")
    nodes = (HierarchyNode("a", None, "lamp"),)
    result = project_hierarchy_references(document_session="session-a", nodes=nodes,
                                         references=(reference,), models=project([]), complete=True)
    assert result.complete is False
    assert result.unresolved_references == (reference,)
    assert result.nodes == nodes


def test_ah_mapping_rejects_other_document_session():
    from plugins.simulation.simulation_backend.domain.live_document_import import project_hierarchy_references
    with pytest.raises(ValueError, match="document_session_changed"):
        project_hierarchy_references(document_session="session-b", nodes=(), references=(),
                                     models=project([]), complete=True)


def test_unobserved_model_does_not_resolve_an_ah_link_from_retained_history():
    from plugins.simulation.simulation_backend.domain.live_document_import import (
        NativeProductReference, project_hierarchy_references,
    )
    from plugins.simulation.simulation_backend.domain.live_hierarchy_sync import HierarchyNode
    inventory = project([], previous=project([model()]), complete=False)
    link = NativeProductReference("ref", "native-a", "lamp-1")
    result = project_hierarchy_references(document_session="session-a",
        nodes=(HierarchyNode("ref", None, "lamp"),), references=(link,), models=inventory, complete=True)
    assert result.complete is False
    assert result.unresolved_references == (link,)


@pytest.mark.parametrize("reference_nodes", [("missing",), ("ref", "ref")])
def test_missing_or_duplicate_ah_reference_target_rejected(reference_nodes):
    from plugins.simulation.simulation_backend.domain.live_document_import import (
        NativeProductReference, project_hierarchy_references,
    )
    from plugins.simulation.simulation_backend.domain.live_hierarchy_sync import HierarchyNode
    with pytest.raises(ValueError, match="hierarchy_reference_target_invalid"):
        project_hierarchy_references(document_session="session-a",
            nodes=(HierarchyNode("ref", None, "lamp"),),
            references=tuple(NativeProductReference(key, "native-a", "lamp-1") for key in reference_nodes),
            models=project([model()]), complete=True)


def test_ten_thousand_hierarchies_share_one_model_inventory_index():
    from plugins.simulation.simulation_backend.domain.live_document_import import (
        HierarchyReferenceProjector, NativeProductReference,
    )
    from plugins.simulation.simulation_backend.domain.live_hierarchy_sync import HierarchyNode

    class CountedInventory(tuple):
        iterations = 0
        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    inventory = project([model(f"native-{i}") for i in range(1000)])
    counted = CountedInventory(inventory.instances)
    resolver = HierarchyReferenceProjector(replace(inventory, instances=counted))
    for index in range(10_000):
        result = resolver.project(document_session="session-a",
            nodes=(HierarchyNode(f"node-{index}", None, "lamp"),),
            references=(NativeProductReference(f"node-{index}", "native-999", "lamp-1"),), complete=True)
        assert result.complete
        assert result.nodes[0].insertion_instance_id == inventory.instances[-1].insertion_instance_id
    assert counted.iterations == 1
