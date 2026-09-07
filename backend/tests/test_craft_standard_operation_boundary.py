from __future__ import annotations

import ast
import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/std_op.py"
AI00_LEVEL_MIGRATION = ROOT / "backend/db/migrations/domains/craft/0008_standard_operation_ai00_level.sql"
GBOP_MATCH_MIGRATION = ROOT / "backend/db/migrations/domains/craft/0009_standard_operation_gbop_match_fields.sql"


def _functions():
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }


def test_standard_operation_routes_use_gateway_boundary():
    functions = _functions()
    expected = (
        "list_operations", "get_operation", "create_operation", "update_operation",
        "delete_operation", "publish_operation", "deprecate_operation",
    )
    for name in expected:
        node = functions[name]
        assert isinstance(node, ast.AsyncFunctionDef)
        literals = {item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)}
        names = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        assert "_invoke_standard_operation" in names
        assert "get_conn" not in names
        assert any(value.startswith("craft.standard_operation.") for value in literals)


def test_standard_operation_capability_operations_are_closed_and_bounded():
    from plugins.craft.craft_backend.capabilities.standard_operation import (
        CHANGE_OPERATIONS,
        READ_OPERATIONS,
    )

    assert READ_OPERATIONS == ("list", "get")
    assert CHANGE_OPERATIONS == ("create", "update", "delete", "publish", "deprecate")


def test_standard_operation_list_reads_the_owned_library_table(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.craft.craft_backend.capabilities import standard_operation

    row = {
        "gid": "sop_1",
        "display_id": "S-C00000001",
        "code": "OP-001",
        "name": "拧紧螺栓",
        "status": "active",
        "standard_time": 30,
        "importance": "high",
        "description": "",
        "level": "7",
        "ai00_level": 4,
        "vpps_attr": None,
        "vpps": None,
        "vpps_desc": None,
        "torque_importance": None,
        "vehicle_model": None,
        "parent_vpps": None,
        "share_scope": "team",
        "version": 1,
        "created_by": "user-1",
        "created_at": "2026-09-07T00:00:00",
        "updated_at": "2026-09-07T00:00:00",
    }

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params):
            assert "workmanship_craft_standard_operations" in sql

        def fetchall(self):
            return [row]

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_get_conn():
        yield Connection()

    monkeypatch.setattr(standard_operation, "get_conn", fake_get_conn)

    output = standard_operation.read_standard_operation(
        {"operation": "list"},
        CapabilityContext(user_gid="user-1", team_gid="team-1"),
    )

    assert output.data["items"] == [row]


def test_standard_operation_keeps_source_level_and_ai00_level_separate():
    from plugins.craft.craft_backend.capabilities import standard_operation
    from plugins.craft.craft_backend.routers.std_op import CreateOpBody, UpdateOpBody

    assert "level" in standard_operation._FIELDS
    assert "ai00_level" in standard_operation._FIELDS

    created = CreateOpBody(code="VPPS-1", name="工序", level="7", ai00_level=4)
    assert created.level == "7"
    assert created.ai00_level == 4

    updated = UpdateOpBody(level="8", ai00_level=5)
    assert updated.level == "8"
    assert updated.ai00_level == 5

    migration = AI00_LEVEL_MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS `ai00_level` INT NULL" in migration


def test_standard_operation_contract_declares_ai00_level():
    from plugins.craft.craft_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS

    input_schema = INPUT_SCHEMAS[("craft.standard_operation.change.apply", 1)]
    assert input_schema["properties"]["record"]["properties"]["ai00_level"] == {"type": "integer"}
    output_schema = OUTPUT_SCHEMAS[("craft.standard_operation.read", 1)]
    assert output_schema["properties"]["items"]["items"]["properties"]["ai00_level"] == {
        "type": ["integer", "null"]
    }


def test_standard_operation_preserves_gbop_import_and_matching_fields():
    from plugins.craft.craft_backend.capabilities import standard_operation
    from plugins.craft.craft_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS

    string_fields = {
        "component_type", "bom_row", "parent_bom_row", "process_vpps",
        "operation_vpps", "vpps_part", "match_tag",
    }
    assert string_fields <= set(standard_operation._FIELDS)
    assert "part_feed" in standard_operation._FIELDS

    input_props = INPUT_SCHEMAS[("craft.standard_operation.change.apply", 1)]["properties"]["record"]["properties"]
    output_props = OUTPUT_SCHEMAS[("craft.standard_operation.read", 1)]["properties"]["items"]["items"]["properties"]
    assert string_fields <= set(input_props)
    assert string_fields <= set(output_props)
    assert input_props["part_feed"] == {"type": "boolean"}
    assert output_props["part_feed"] == {"type": "boolean"}

    migration = GBOP_MATCH_MIGRATION.read_text(encoding="utf-8")
    for field in (*sorted(string_fields), "part_feed"):
        assert f"`{field}`" in migration


def test_create_route_omits_unset_optional_nulls():
    from plugins.craft.craft_backend.routers import std_op

    invoke = AsyncMock(return_value={"success": True, "gid": "sop-1"})
    original = std_op._invoke_standard_operation
    std_op._invoke_standard_operation = invoke
    try:
        asyncio.run(std_op.create_operation(
            std_op.CreateOpBody(code="OP-1", name="工序", level="7", ai00_level=4),
            SimpleNamespace(headers={}), {}, object(), object(),
        ))
    finally:
        std_op._invoke_standard_operation = original

    record = invoke.await_args.kwargs["record"]
    assert record["level"] == "7"
    assert record["ai00_level"] == 4
    assert "importance" not in record
    assert "vpps" not in record


def test_standard_operation_compatibility_returns_direct_capability_payload(monkeypatch):
    from plugins.craft.craft_backend.routers import std_op

    async def invoke(*_args, **_kwargs):
        return SimpleNamespace(ok=True, data={"items": [{"gid": "sop-1"}]}, error=None)

    monkeypatch.setattr(std_op, "invoke_compatibility", invoke)
    monkeypatch.setattr(std_op, "build_web_compatibility_envelope", lambda *_args, **_kwargs: object())

    result = asyncio.run(std_op._invoke_standard_operation(
        SimpleNamespace(headers={}), {}, object(), object(),
        "craft.standard_operation.read", "list",
    ))

    assert result == {"items": [{"gid": "sop-1"}]}
