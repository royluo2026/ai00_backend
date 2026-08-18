from __future__ import annotations

import pytest

from backend.capabilities.models_next import CapabilityBusinessError
from plugins.craft.craft_backend.services.bop_navigation import (
    BopNavigationRepository, decode_cursor, encode_cursor,
)


class ScriptedCursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []
        self.current = None

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()):
        self.statements.append((" ".join(sql.split()), tuple(params)))
        self.current = self.responses.pop(0)
    def fetchone(self): return self.current.get("one")
    def fetchall(self): return self.current.get("all", [])


class ScriptedConnection:
    def __init__(self, responses): self.cursor_value = ScriptedCursor(responses)
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value


def _repository(responses):
    connection = ScriptedConnection(responses)
    return BopNavigationRepository(lambda: connection), connection.cursor_value


def test_cursor_is_opaque_stable_and_rejects_tampering():
    cursor = encode_cursor(1.5, "gid_002")

    assert decode_cursor(cursor) == (1.5, "gid_002")
    assert "gid_002" not in cursor
    for invalid in ("", "not-base64", encode_cursor(1, "gid") + "x"):
        with pytest.raises(CapabilityBusinessError) as raised:
            decode_cursor(invalid)
        assert raised.value.code == "invalid_cursor"


def test_work_package_uses_keyset_page_and_batches_links_for_returned_gids_only(monkeypatch):
    from plugins.craft.craft_backend.services.execution_structure import ExecutionStructureRepository
    monkeypatch.setattr(
        ExecutionStructureRepository, "load_bop_aggregate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("full aggregate forbidden")),
    )
    rows = [
        {"gid": "e1", "parent_gid": "line1", "node_type": "process", "sort_order": 1.0,
         "title": "P1", "vpps": "v1"},
        {"gid": "e2", "parent_gid": "e1", "node_type": "operation", "sort_order": 1.0,
         "title": "O1", "vpps": "v2"},
        {"gid": "e3", "parent_gid": "e1", "node_type": "part", "sort_order": 2.0,
         "title": "Part", "vpps": None},
    ]
    repository, cursor = _repository([
        {"one": {"revision": 7}},
        {"one": {"gid": "line1", "node_type": "line_process"}},
        {"all": rows},
        {"one": {"total_count": 3}},
        {"all": [
            {"entry_gid": "e1", "link_type": "project_tools", "entity_gid": "tool1", "is_primary": 1},
            {"entry_gid": "e2", "link_type": "pbom_part", "entity_gid": "part1", "is_primary": 1},
        ]},
        {"one": {"revision": 7}},
    ])

    result = repository.get_work_package_page(
        "version1", 7, "line", "line1", cursor=None, page_size=2,
    )

    assert [item["gid"] for item in result["nodes"]] == ["e1", "e2"]
    assert result["nodes"][0]["tool_refs"] == ["tool:tool1"]
    assert result["nodes"][1]["part_refs"] == ["part:part1"]
    assert result["next_cursor"] == encode_cursor(1.0, "e2")
    page_sql, page_params = cursor.statements[2]
    assert "sort_order > %s OR (e.sort_order = %s AND e.gid > %s)" in page_sql
    assert page_params[-1] == 3
    link_sql, link_params = cursor.statements[4]
    assert "entry_gid IN (%s,%s)" in link_sql
    assert "e3" not in link_params
    assert link_params[-2:] == ("e1", "e2")


def test_revision_change_after_page_assembly_returns_conflict():
    repository, _cursor = _repository([
        {"one": {"revision": 7}},
        {"one": {"gid": "line1", "node_type": "line_process"}},
        {"all": []},
        {"one": {"total_count": 0}},
        {"one": {"revision": 8}},
    ])

    with pytest.raises(CapabilityBusinessError) as raised:
        repository.get_work_package_page(
            "version1", 7, "line", "line1", cursor=None, page_size=2,
        )
    assert raised.value.code == "revision_conflict"


def test_outline_is_bounded_and_counts_only_current_page_lines():
    lines = [
        {"gid": "line1", "parent_gid": "root", "node_type": "line_process", "sort_order": 1.0, "title": "L1"},
        {"gid": "line2", "parent_gid": "root", "node_type": "line_process", "sort_order": 2.0, "title": "L2"},
    ]
    repository, cursor = _repository([
        {"one": {"revision": 3}},
        {"one": {"gid": "root", "parent_gid": None, "node_type": "factory_bop", "sort_order": 0, "title": "Root"}},
        {"all": lines},
        {"one": {"total_count": 2}},
        {"all": [
            {"root_gid": "line1", "node_type": "station_process", "node_count": 10},
            {"root_gid": "line2", "node_type": "operation", "node_count": 20},
        ]},
        {"one": {"revision": 3}},
    ])

    result = repository.get_outline_page("version1", 3, cursor=None, page_size=2)

    assert result["total_lines"] == 2
    assert result["lines"][0]["counts"] == {"station_process": 10}
    count_params = cursor.statements[4][1]
    assert count_params[1:-1] == ("line1", "line2")


def test_page_size_and_scope_kind_are_rejected_before_sql():
    repository, cursor = _repository([])
    with pytest.raises(CapabilityBusinessError) as page_error:
        repository.get_outline_page("version1", 1, cursor=None, page_size=101)
    assert page_error.value.code == "invalid_page_size"
    with pytest.raises(CapabilityBusinessError) as scope_error:
        repository.get_work_package_page(
            "version1", 1, "role", "scope1", cursor=None, page_size=10,
        )
    assert scope_error.value.code == "invalid_scope_kind"
    assert cursor.statements == []
