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


class _Cursor:
    rowcount = 0

    def __init__(self):
        self.entry_reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=()):
        self.sql = " ".join(sql.split())
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
