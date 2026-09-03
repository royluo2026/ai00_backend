import json
from datetime import datetime
from pathlib import Path

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.capabilities.validation_next import validate_payload
from plugins.craft.craft_backend.capabilities import bop_entry_change
from plugins.craft.craft_backend.capabilities.bop_entry_change import apply_bop_entry_change
from plugins.craft.craft_backend.capabilities.contracts import output_schema_for


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/entries.py")


def test_entry_change_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.entry.change.apply"') == 1
    assert "def _legacy_update_entry" in source
    assert "def _legacy_delete_entry" in source


def test_entry_change_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_entry_change({"operation": "create"}, object())


def test_entry_change_validates_update_payload_before_io() -> None:
    with pytest.raises(ValueError, match="updates must be a non-empty object"):
        apply_bop_entry_change({"operation": "update", "entry_gid": "e1", "updates": {}}, object())


def test_entry_change_contract_keeps_ai00_level_and_delete_result() -> None:
    schema = output_schema_for("craft.bop.entry.change.apply", 1)

    validate_payload(schema, {
        "data": {"gid": "e1", "version_gid": "v1", "ai00_level": 2},
        "version_gid": "v1",
    }, label="output")
    validate_payload(schema, {
        "data": {"gid": "e1", "deleted": True},
        "version_gid": "v1",
    }, label="output")

    data_schema = schema["properties"]["data"]
    assert data_schema["additionalProperties"] is False
    assert "ai00_level" in data_schema["properties"]
    assert "deleted" in data_schema["properties"]


def test_entry_change_contract_accepts_both_process_picture_fields() -> None:
    from plugins.craft.craft_backend.capabilities.contracts import input_schema_for

    schema = input_schema_for("craft.bop.entry.change.apply", 1)
    updates = schema["properties"]["updates"]["properties"]

    assert "process_flow_pic" in updates
    assert "process_chart_pic" in updates
    output = output_schema_for("craft.bop.entry.change.apply", 1)
    assert "process_flow_pic" in output["properties"]["data"]["properties"]
    assert "process_chart_pic" in output["properties"]["data"]["properties"]


class _Cursor:
    rowcount = 0

    def __init__(self):
        self.entry_reads = 0
        self.sqls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=()):
        self.sql = " ".join(sql.split())
        self.sqls.append(self.sql)
        if self.sql.startswith("SELECT e.gid"):
            self.entry_reads += 1
        self.rowcount = 0 if self.sql.startswith("UPDATE workmanship_bop_bop_entries") else 1

    def fetchone(self):
        if self.sql.startswith("SELECT e.gid"):
            if self.entry_reads > 1:
                return {
                    "gid": "e1", "version_gid": "v1", "parent_gid": None,
                    "node_type": "process", "sort_order": 20, "level": 4,
                    "ai00_level": 4, "title": "Process", "updated_at": datetime(2026, 9, 3, 12, 0),
                }
            return {
                "gid": "e1", "version_gid": "v1", "parent_gid": None,
                "node_type": "process", "title": "Process", "vpps": None,
                "vpps_desc": None, "parent_bop_title": None, "meta": {},
            }
        if self.sql.startswith("SELECT *"):
            return {"gid": "e1", "sort_order": 20, "updated_at": datetime(2026, 9, 3, 12, 0)}
        if self.sql.startswith("SELECT 1"):
            return {"present": 1}
        return None


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1


def test_unchanged_entry_update_returns_json_safe_data(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(bop_entry_change, "get_craft_conn", lambda: connection)
    monkeypatch.setattr(bop_entry_change, "_ensure_editable", lambda *_args: None)
    monkeypatch.setattr(bop_entry_change, "_log_entry_op", lambda *_args, **_kwargs: None)

    result = apply_bop_entry_change(
        {"operation": "update", "entry_gid": "e1", "updates": {"sort_order": 20}},
        CapabilityContext(user_gid="admin-1", active_roles=("super_admin",)),
    )

    assert json.loads(json.dumps(result))["data"]["updated_at"] == "2026-09-03T12:00:00"
    assert connection.commits == 1


@pytest.mark.parametrize("field", ("process_flow_pic", "process_chart_pic"))
def test_process_picture_updates_are_persisted_to_the_matching_column(monkeypatch, field) -> None:
    connection = _Connection()
    monkeypatch.setattr(bop_entry_change, "get_craft_conn", lambda: connection)
    monkeypatch.setattr(bop_entry_change, "_ensure_editable", lambda *_args: None)
    monkeypatch.setattr(bop_entry_change, "_log_entry_op", lambda *_args, **_kwargs: None)

    apply_bop_entry_change(
        {"operation": "update", "entry_gid": "e1", "updates": {field: [{"url": "/image.png"}]}},
        CapabilityContext(user_gid="admin-1", active_roles=("super_admin",)),
    )

    assert any(f"SET {field}=%s" in sql for sql in connection.cursor_value.sqls)


def test_delete_retires_owned_entity_and_link_visibility_in_same_transaction(monkeypatch) -> None:
    class DeleteCursor(_Cursor):
        def __init__(self):
            super().__init__()
            self.sqls = []

        def execute(self, sql, params=()):
            super().execute(sql, params)
            self.sqls.append(self.sql)
            if self.sql.startswith("UPDATE workmanship_bop_bop_entries"):
                self.rowcount = 1

        def fetchone(self):
            if self.sql.startswith("SELECT e.gid"):
                return {
                    "gid": "e1", "version_gid": "v1", "parent_gid": None,
                    "node_type": "bop_station", "title": "Station", "vpps": None,
                    "vpps_desc": None, "parent_bop_title": None, "meta": {},
                }
            if self.sql.startswith("SELECT parent_gid"):
                return {"parent_gid": None, "title": "Station", "node_type": "bop_station", "vpps": None}
            return None

        def fetchall(self):
            if self.sql.startswith("SELECT entity_gid"):
                return [{"entity_gid": "station-1", "link_type": "bop_station", "is_primary": True}]
            return []

    connection = _Connection()
    connection.cursor_value = DeleteCursor()
    monkeypatch.setattr(bop_entry_change, "get_craft_conn", lambda: connection)
    monkeypatch.setattr(bop_entry_change, "_ensure_editable", lambda *_args: None)
    monkeypatch.setattr(bop_entry_change, "_log_entry_op", lambda *_args, **_kwargs: None)

    result = apply_bop_entry_change(
        {"operation": "delete", "entry_gid": "e1"},
        CapabilityContext(user_gid="admin-1", active_roles=("super_admin",)),
    )

    sqls = connection.cursor_value.sqls
    assert any("UPDATE workmanship_bop_bop_station SET is_deleted=TRUE, deleted_at=NOW()" in sql for sql in sqls)
    assert any("UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE, deleted_at=NOW()" in sql for sql in sqls)
    assert result["data"] == {"deleted": True, "gid": "e1"}
    assert connection.commits == 1
