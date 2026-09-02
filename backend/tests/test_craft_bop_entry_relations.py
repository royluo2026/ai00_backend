from __future__ import annotations

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.business_definition import substantive_business_definition_errors
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.bop_entry_relations import (
    BopEntryRelationRepository, decode_relation_cursor, encode_relation_cursor,
)


def _registrations():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    return {(item.spec.id, item.spec.version): item for item in registry.snapshot()}


def test_atomic_bop_relation_reads_are_registered_and_bounded():
    registrations = _registrations()

    relation = registrations[("craft.bop.entry.relation.list", 1)].descriptor
    detail = registrations[("craft.bop.linked_entity.detail.get", 1)].descriptor
    assert relation.owner_domain == detail.owner_domain == "craft"
    assert relation.input_schema["additionalProperties"] is False
    assert detail.input_schema["additionalProperties"] is False
    assert relation.execution_budget.max_page_size == 200
    assert relation.execution_budget.max_output_bytes == 1024 * 1024
    assert detail.execution_budget.max_output_bytes == 512 * 1024
    assert relation.resource_selectors[0].payload_path == "version_gid"
    assert detail.resource_selectors[0].payload_path == "version_gid"
    assert substantive_business_definition_errors(relation) == ()
    assert substantive_business_definition_errors(detail) == ()


class _Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.current = None
        self.statements = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False

    def execute(self, sql, params=()):
        self.statements.append((" ".join(sql.split()), tuple(params)))
        self.current = self.responses.pop(0)

    def fetchone(self): return self.current.get("one")
    def fetchall(self): return self.current.get("all", [])


class _Connection:
    def __init__(self, responses): self.cursor_value = _Cursor(responses)
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value


def _repository(responses):
    connection = _Connection(responses)
    return BopEntryRelationRepository(lambda: connection), connection.cursor_value


def test_relation_cursor_is_opaque_and_rejects_tampering():
    cursor = encode_relation_cursor("entry-1", "link-1")

    assert decode_relation_cursor(cursor) == ("entry-1", "link-1")
    assert "entry-1" not in cursor
    with pytest.raises(CapabilityBusinessError) as raised:
        decode_relation_cursor(cursor + "x")
    assert raised.value.code == "invalid_cursor"


def test_relation_list_is_keyset_paged_and_projects_closed_summaries():
    repository, cursor = _repository([
        {"one": {"revision": 3}},
        {"one": {"gid": "entry-root"}},
        {"all": [
            {
                "link_gid": "link-1", "source_entry_gid": "entry-1", "source_entry_title": "P1",
                "link_type": "pbom_part", "entity_gid": "part-1", "is_primary": 1,
                "is_inherited": 0, "created_at": None,
                "entity_data": '{"gid":"part-1","part_no":"P-1","name":"Part"}',
            },
            {
                "link_gid": "link-2", "source_entry_gid": "entry-1", "source_entry_title": "P1",
                "link_type": "resource_tool", "entity_gid": "tool-1", "is_primary": 0,
                "is_inherited": 1, "created_at": None,
                "entity_data": '{"gid":"tool-1","resource_type":"tool","code":"T-1","name":"Tool"}',
            },
            {
                "link_gid": "link-3", "source_entry_gid": "entry-2", "source_entry_title": "P2",
                "link_type": "custom_relation", "entity_gid": "custom-1", "is_primary": 0,
                "is_inherited": 0, "created_at": None, "entity_data": None,
            },
        ]},
        {"one": {"revision": 3}},
    ])

    result = repository.list_relations(
        "version-1", 3, "entry-root", recursive=True, cursor=None, page_size=2,
    )

    assert [item["link_gid"] for item in result["items"]] == ["link-1", "link-2"]
    assert result["items"][0]["target_ref"] == {"type": "pbom_part", "gid": "part-1"}
    assert result["items"][0]["target_summary"]["part_no"] == "P-1"
    assert result["items"][1]["is_inherited"] is True
    assert result["next_cursor"] == encode_relation_cursor("entry-1", "link-2")
    page_sql, page_params = cursor.statements[2]
    assert "WITH RECURSIVE scoped" in page_sql
    assert "l.version_gid=%s" in page_sql
    assert "l.deleted_at IS NULL" in page_sql
    assert page_params[-1] == 3


def test_direct_relation_list_does_not_expand_descendants():
    repository, cursor = _repository([
        {"one": {"revision": 2}},
        {"one": {"gid": "entry-1"}},
        {"all": []},
        {"one": {"revision": 2}},
    ])

    result = repository.list_relations(
        "version-1", 2, "entry-1", recursive=False, cursor=None, page_size=10,
    )

    assert result["items"] == []
    assert "WITH RECURSIVE" not in cursor.statements[2][0]


def test_linked_entity_detail_closes_unknown_or_missing_target():
    repository, _cursor = _repository([
        {"one": {"revision": 4}},
        {"one": {
            "link_gid": "link-1", "entry_gid": "entry-1", "version_gid": "version-1",
            "link_type": "custom_relation", "entity_gid": "custom-1", "is_primary": 0,
            "entity_data": None,
        }},
        {"one": {"revision": 4}},
    ])

    result = repository.get_linked_entity_detail("version-1", 4, "link-1")

    assert result["readable"] is False
    assert result["entity_data"] is None
    assert result["link"]["link_gid"] == "link-1"


def test_relation_reads_reject_invalid_bounds_and_deleted_links():
    repository, cursor = _repository([])
    with pytest.raises(CapabilityBusinessError) as raised:
        repository.list_relations(
            "version-1", 1, "entry-1", recursive=False, cursor=None, page_size=201,
        )
    assert raised.value.code == "invalid_page_size"
    assert cursor.statements == []

    repository, _cursor = _repository([
        {"one": {"revision": 1}},
        {"one": None},
    ])
    with pytest.raises(CapabilityBusinessError) as raised:
        repository.get_linked_entity_detail("version-1", 1, "deleted-link")
    assert raised.value.code == "link_not_found"
