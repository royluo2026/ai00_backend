import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.bop_structure import (
    get_execution_structure,
    get_linked_parts,
    get_work_package,
    preview_execution_structure,
)
from plugins.craft.craft_backend.services.execution_structure import (
    BopAggregate,
    build_execution_structure,
    repository,
)


def _aggregate(*, published: bool = True, revision: int = 7) -> BopAggregate:
    return BopAggregate(
        version={
            "gid": "v1",
            "project_gid": "p1",
            "revision": revision,
            "status": "baseline" if published else "active",
            "published_at": "2026-08-05T10:00:00Z" if published else None,
            "updated_at": "2026-08-05T09:00:00Z",
        },
        entries=(
            {"gid": "line-1", "parent_gid": None, "node_type": "line_process", "sort_order": 20, "title": "Line A"},
            {"gid": "station-1", "parent_gid": "line-1", "node_type": "station_process", "sort_order": 10, "title": "Station 10"},
            {"gid": "op-2", "parent_gid": "station-1", "node_type": "operation", "sort_order": 20, "title": "Fasten"},
            {"gid": "op-1", "parent_gid": "station-1", "node_type": "operation", "sort_order": 10, "title": "Position"},
        ),
        links=(
            {"entry_gid": "op-1", "link_type": "pbom_part", "entity_gid": "part-1", "is_primary": True, "entity_data": {"part_no": "A-1", "name": "Bracket"}},
            {"entry_gid": "op-2", "link_type": "project_tools", "entity_gid": "tool-1", "entity_data": {"name": "Torque wrench"}},
        ),
    )


def test_provider_registers_four_approved_structure_capabilities():
    registry = CapabilityRegistry()
    register_capabilities(registry)

    for capability_id in (
        "craft.bop.execution_structure.get",
        "craft.bop.execution_structure.preview",
        "craft.bop.linked_parts.get",
        "craft.bop.work_package.get",
    ):
        assert registry.get(capability_id).spec.owner == "craft"

    linked_parts = registry.get("craft.bop.linked_parts.get").spec
    assert "craft.pbom.part" in linked_parts.subject_concepts
    assert "craft.execution_structure" not in linked_parts.subject_concepts


def test_official_structure_rejects_draft():
    with patch.object(repository, "load_bop_aggregate", return_value=_aggregate(published=False)):
        with pytest.raises(CapabilityBusinessError, match="published"):
            get_execution_structure(
                {"version_gid": "v1"},
                CapabilityContext(user_gid="u1"),
            )


def test_preview_requires_matching_expected_revision():
    with patch.object(repository, "load_bop_aggregate", return_value=_aggregate(revision=7)):
        with pytest.raises(ValueError, match="expected_revision"):
            preview_execution_structure(
                {"version_gid": "v1"},
                CapabilityContext(user_gid="u1"),
            )
        with pytest.raises(CapabilityBusinessError) as caught:
            preview_execution_structure(
                {"version_gid": "v1", "expected_revision": 6},
                CapabilityContext(user_gid="u1"),
            )
    assert caught.value.code == "revision_conflict"


def test_work_package_scope_is_allowlisted():
    with pytest.raises(ValueError, match="scope.kind"):
        get_work_package(
            {"version_gid": "v1", "scope": {"kind": "factory", "gid": "f1"}},
            CapabilityContext(user_gid="u1"),
        )


def test_structure_hash_is_deterministic_for_input_order():
    first = _aggregate()
    second = BopAggregate(
        version=copy.deepcopy(first.version),
        entries=tuple(reversed(copy.deepcopy(first.entries))),
        links=tuple(reversed(copy.deepcopy(first.links))),
    )
    with patch.object(repository, "load_bop_aggregate", side_effect=[first, second]):
        one = build_execution_structure("v1", expected_revision=None, preview=False)
        two = build_execution_structure("v1", expected_revision=None, preview=False)

    assert one["content_hash"] == two["content_hash"]
    assert [item["operation_id"] for item in one["operations"]] == ["op-1", "op-2"]
    assert one["operations"][1]["predecessor_ids"] == ["op-1"]


def test_linked_parts_reports_usage_locations():
    with patch.object(repository, "load_bop_aggregate", return_value=_aggregate()):
        result = get_linked_parts(
            {"version_gid": "v1"},
            CapabilityContext(user_gid="u1"),
        )

    assert result.data["items"] == [
        {
            "part_gid": "part-1",
            "part_no": "A-1",
            "name": "Bracket",
            "usage": [{"entry_gid": "op-1", "entry_title": "Position"}],
        }
    ]


def test_linked_parts_is_bounded_with_cursor_pagination():
    aggregate = _aggregate()
    aggregate = BopAggregate(
        version=aggregate.version,
        entries=aggregate.entries,
        links=(
            aggregate.links[0],
            {**aggregate.links[0], "entry_gid": "op-2", "entity_gid": "part-2", "entity_data": {"part_no": "A-2", "name": "Bolt"}},
        ),
    )
    with patch.object(repository, "load_bop_aggregate", return_value=aggregate):
        first = get_linked_parts({"version_gid": "v1", "page_size": 1}, CapabilityContext(user_gid="u1"))
        second = get_linked_parts({"version_gid": "v1", "page_size": 1, "cursor": first.data["next_cursor"]}, CapabilityContext(user_gid="u1"))

    assert first.data["total"] == 2
    assert len(first.data["items"]) == 1
    assert first.data["next_cursor"] == "1"
    assert [item["part_gid"] for item in second.data["items"]] == ["part-2"]
    assert second.data["next_cursor"] is None


def test_linked_parts_exposes_legacy_compatibility_rows():
    aggregate = _aggregate()
    with patch.object(repository, "load_bop_aggregate", return_value=aggregate):
        result = get_linked_parts(
            {"version_gid": "v1"},
            CapabilityContext(user_gid="u1"),
        )

    assert result.data["legacy_items"] == [
        {
            "gid": "part-1",
            "name": "Bracket",
            "parent_gid": None,
            "part_no": "A-1",
            "quantity": None,
            "unit": None,
            "snapshot_gid": None,
            "material": None,
            "meta": {},
            "entry_gid": "op-1",
            "link_gid": None,
            "created_at": None,
        }
    ]


def test_linked_parts_repository_uses_declared_pbom_columns():
    source = Path("plugins/craft/craft_backend/services/execution_structure.py").read_text(encoding="utf-8")
    query = source[source.index('"SELECT l.gid AS link_gid'):source.index('"WHERE l.version_gid = %s AND l.is_deleted = 0"')]

    for nonexistent in ("p.updated_at", "p.parent_part_gid", "p.node_type", "p.bom_row_id", "p.seq_no", "p.part_number"):
        assert nonexistent not in query


def test_linked_parts_exposes_legacy_pbom_rows():
    aggregate = _aggregate()
    aggregate = BopAggregate(
        version=aggregate.version,
        entries=aggregate.entries,
            links=(
            {
                **aggregate.links[0],
                "entity_data": {
                    **aggregate.links[0]["entity_data"],
                    "vpps": "V1",
                    "parent_part_gid": "parent-1",
                    "node_type": "part",
                    "bom_row_id": "row-1",
                    "seq_no": 3,
                    "quantity": 2,
                    "unit": "pcs",
                    "part_number": "A-1",
                    "created_at": "2026-08-19T00:00:00+00:00",
                    "updated_at": "2026-08-19T01:00:00+00:00",
                },
            },
                aggregate.links[1],
            ),
    )
    with patch.object(repository, "load_bop_aggregate", return_value=aggregate):
        result = get_linked_parts({"version_gid": "v1"}, CapabilityContext(user_gid="u1"))

    assert result.data["legacy_pbom_items"] == [
        {
            "gid": "part-1",
            "title": "Bracket",
            "vpps": "V1",
            "parent_part_gid": "parent-1",
            "node_type": "part",
            "bom_row_id": "row-1",
            "seq_no": 3,
            "quantity": 2,
            "unit": "pcs",
            "part_number": "A-1",
            "created_at": "2026-08-19T00:00:00+00:00",
            "updated_at": "2026-08-19T01:00:00+00:00",
        }
    ]
