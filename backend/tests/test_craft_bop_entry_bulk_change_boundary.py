from pathlib import Path

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.craft.craft_backend.capabilities.bop_entry_bulk_change import apply_bop_entry_bulk_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/entries.py")


def test_entry_bulk_routes_use_one_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.entry.bulk.change.apply"') == 1
    for name in ("create_entry", "purge_version_entries", "import_tc_entries", "copy_entries_from", "copy_entries_from_gbop", "auto_link_entries", "patch_entity_detail", "rollback_entry_history"):
        assert f"def _legacy_{name}" in source


def test_entry_bulk_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_entry_bulk_change({"operation": "delete"}, object())


def test_entry_bulk_validates_required_fields_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_entry_bulk_change({"operation": "import_tc"}, object())


class _ImportCursor:
    def __init__(self, *, fail_links: bool = False):
        self.fail_links = fail_links
        self._one = None
        self._many = []
        self.entry_rows = []
        self.link_rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self._one = None
        self._many = []
        if normalized.startswith("SELECT project_gid, frozen_at"):
            self._one = {
                "project_gid": "project-1", "frozen_at": None,
                "pbom_version_gid": "pbom-1", "bop_name": "Assembly",
            }
        elif normalized.startswith("SELECT gid FROM workmanship_bop_bop_entries"):
            self._many = []
        elif normalized.startswith("SELECT node_type, title"):
            self._many = []
        elif normalized.startswith("SELECT gid FROM workmanship_craft_resource_requirements"):
            self._one = {"gid": f"resource-{params[0]}"}

    def executemany(self, sql, rows):
        normalized = " ".join(sql.split())
        if normalized.startswith("INSERT INTO workmanship_bop_bop_entries"):
            self.entry_rows = list(rows)
        elif normalized.startswith("INSERT INTO workmanship_bop_bop_entry_links"):
            if self.fail_links:
                raise RuntimeError("injected link failure")
            self.link_rows = list(rows)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _ImportConnection:
    def __init__(self, *, fail_links: bool = False):
        self.cursor_value = _ImportCursor(fail_links=fail_links)
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_args):
        if exc_type is not None:
            self.rollbacks += 1
            self.cursor_value.entry_rows = []
            self.cursor_value.link_rows = []
        return False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1


def _tc_import_rows():
    return [
        {"_level": 1, "node_type": "line_process", "title": "Assembly line"},
        {"_level": 2, "node_type": "socket_need", "title": "Socket", "code": "S-01"},
        {"_level": 2, "node_type": "tool_need", "title": "Tool", "code": "T-01"},
        {"_level": 2, "node_type": "fixture_need", "title": "Fixture", "code": "F-01"},
        {"_level": 2, "node_type": "equipment_need", "title": "Equipment", "code": "E-01"},
    ]


def _context():
    return CapabilityContext(
        user_gid="user-1", request_id="request-1", permissions=("craft.write",),
    )


def test_tc_import_commits_entries_and_independent_resource_links(monkeypatch) -> None:
    from plugins.craft.craft_backend.routers._bop import entries

    connection = _ImportConnection()
    gids = iter(f"gid-{index}" for index in range(100))
    monkeypatch.setattr(entries, "get_conn", lambda: connection)
    monkeypatch.setattr(entries, "next_gid", lambda: next(gids))

    result = apply_bop_entry_bulk_change(
        {"operation": "import_tc", "version_gid": "version-1", "rows": _tc_import_rows()},
        _context(),
    )

    assert result["data"] == {"count": 5, "skipped": 0, "replaced": 0}
    assert connection.commits == 1
    assert len(connection.cursor_value.entry_rows) == 5
    assert [row[4] for row in connection.cursor_value.link_rows] == [
        "resource_socket", "resource_tool", "resource_fixture", "resource_equipment",
    ]


def test_tc_import_rolls_back_entries_when_resource_link_write_fails(monkeypatch) -> None:
    from fastapi import HTTPException
    from plugins.craft.craft_backend.routers._bop import entries

    connection = _ImportConnection(fail_links=True)
    gids = iter(f"gid-{index}" for index in range(100))
    monkeypatch.setattr(entries, "get_conn", lambda: connection)
    monkeypatch.setattr(entries, "next_gid", lambda: next(gids))

    with pytest.raises(HTTPException, match="injected link failure"):
        apply_bop_entry_bulk_change(
            {"operation": "import_tc", "version_gid": "version-1", "rows": _tc_import_rows()},
            _context(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.cursor_value.entry_rows == []
    assert connection.cursor_value.link_rows == []
