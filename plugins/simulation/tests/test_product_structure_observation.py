import pytest

from plugins.simulation.simulation_backend.domain.product_structure_observation import (
    GeometryReference,
    ObservationPage,
    OccurrenceRecord,
    ProductStructureValidationError,
    SourceSelector,
    validate_observation_pages,
)


def node(identity, parent=None, *, item_revision="rev-A", order=0):
    return OccurrenceRecord(
        occurrence_id=identity, parent_occurrence_id=parent, depth=0 if parent is None else 1,
        child_order=order, name=identity, item_uid="item-A", item_id="A",
        item_revision_uid=item_revision, revision_id="01", component_type="ItemRevision",
        owning_user="owner", owning_group="group", transform=None, bbox=None,
        geometry_refs=(GeometryReference("dataset-A", "file-A", "a.jt"),),
    )


def test_repeated_product_revision_remains_two_occurrences():
    root = node("root")
    left = node("left", "root", item_revision="same-revision", order=0)
    right = node("right", "root", item_revision="same-revision", order=1)

    result = validate_observation_pages((ObservationPage(0, None, (root, left, right)),), 3)

    assert tuple(item.occurrence_id for item in result) == ("root", "left", "right")


def test_duplicate_occurrence_identity_is_rejected_across_pages():
    pages = (ObservationPage(0, 1, (node("root"),)), ObservationPage(1, None, (node("root"),)))
    with pytest.raises(ProductStructureValidationError, match="occurrence_identity_duplicate"):
        validate_observation_pages(pages, 2)


def test_parent_cycle_or_wrong_depth_is_rejected():
    cyclic = (
        OccurrenceRecord(**{**node("a", "b").__dict__, "depth": 1}),
        OccurrenceRecord(**{**node("b", "a").__dict__, "depth": 1}),
    )
    with pytest.raises(ProductStructureValidationError, match="occurrence_graph_invalid"):
        validate_observation_pages((ObservationPage(0, None, cyclic),), 2)


def test_source_identity_uses_configuration_not_display_name():
    first = SourceSelector("tc-test", "uid-A", "rev-A", "view-A", "Latest Working", "2026-09-16T00:00:00Z")
    same = SourceSelector("tc-test", "uid-A", "rev-A", "view-A", "Latest Working", "2026-09-16T00:00:00Z")
    later = SourceSelector("tc-test", "uid-A", "rev-A", "view-A", "Latest Working", "2026-09-17T00:00:00Z")

    assert first.identity_hash == same.identity_hash
    assert first.identity_hash != later.identity_hash
