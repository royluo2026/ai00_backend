from __future__ import annotations

import ast
import json
import hashlib
import sqlite3
from pathlib import Path

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/rules.py"


def test_rule_library_routes_use_gateway_boundary():
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))}
    for name in ("list_rules", "create_rule", "get_rule", "update_rule", "delete_rule"):
        node = functions[name]
        assert isinstance(node, ast.AsyncFunctionDef)
        identifiers = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        assert "_invoke_rule_library" in identifiers
        assert "get_conn" not in identifiers


def test_rule_library_operations_are_closed():
    from plugins.craft.craft_backend.capabilities.rule_library import CHANGE_OPERATIONS, READ_OPERATIONS

    assert READ_OPERATIONS == ("list", "get")
    assert CHANGE_OPERATIONS == ("create", "update", "delete")


def test_rule_library_read_projects_the_canonical_rule_reference():
    from plugins.craft.craft_backend.capabilities.rule_library import _row

    row = _row({"gid": "rule-1", "rule_definition": {"_revision": 1}})

    assert row["rule_gid"] == "rule-1"
    assert row["revision"] == 1
    assert row["rule_reference"] == {"rule_gid": "rule-1", "rule_revision": 1}


def test_committed_rule_reference_fixture_is_the_backend_projection():
    from plugins.craft.craft_backend.capabilities.rule_library import _row

    fixture = ROOT / "backend/tests/fixtures/craft_rule_reference_projection.json"
    value = json.loads(fixture.read_text(encoding="utf-8"))
    projection = _row({"gid": "rule-1", "rule_definition": {"_revision": 1}})

    assert value == {key: projection[key] for key in value}
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == "3fecc9bf124fcb8c279c3bf4c90dea25acf5bbe333bf63638149b81e75aa0da9"


def test_rule_library_create_then_read_preserves_owner_team_and_rule_reference(monkeypatch):
    from plugins.craft.craft_backend.capabilities import rule_library

    stored = {}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params=()):
            if sql.startswith("INSERT INTO"):
                columns = sql.split("(", 1)[1].split(")", 1)[0].split(", ")
                stored.update(dict(zip(columns, params)))
                self.current = None
            else:
                self.current = dict(stored) if stored and params[0] == "rule-1" else None
        def fetchone(self): return self.current
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr(rule_library, "get_conn", lambda: Connection())
    monkeypatch.setattr(rule_library, "next_gid", lambda: "rule-1")
    monkeypatch.setattr(rule_library, "next_display_id", lambda *_: 1)
    context = CapabilityContext(user_gid="owner-1", team_gid="team-a")

    rule_library.change_rule_library({"operation": "create", "record": {"name": "Rule"}}, context)
    result = rule_library.read_rule_library({"operation": "get", "gid": "rule-1"}, context).data["data"]

    assert json.loads(stored["rule_definition"])["_revision"] == 1
    assert json.loads(stored["applicable_scope"]) == {"team_gid": "team-a"}
    assert stored["owner_user_gid"] == stored["creator_gid"] == "owner-1"
    assert result["rule_reference"] == {"rule_gid": "rule-1", "rule_revision": 1}


def test_rule_library_get_uses_the_same_authenticated_visibility_as_list(monkeypatch):
    from plugins.craft.craft_backend.capabilities import rule_library

    statements = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params=()):
            statements.append((sql, params))
        def fetchone(self): return None
        def fetchall(self): return []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(rule_library, "get_conn", lambda: Connection())
    context = CapabilityContext(user_gid="user-1", team_gid="team-1")
    rule_library.read_rule_library({"operation": "list", "limit": 10}, context)
    with pytest.raises(ValueError, match="rule not found"):
        rule_library.read_rule_library({"operation": "get", "gid": "rule-private"}, context)
    list_sql, list_params = statements[0]
    get_sql, get_params = statements[1]
    visibility = "owner_user_gid=%s OR creator_gid=%s OR share_scope='global'"
    assert visibility in list_sql and visibility in get_sql
    assert "JSON_UNQUOTE(JSON_EXTRACT(applicable_scope, '$.team_gid'))=%s" in get_sql
    assert list_params[:3] == ("user-1", "user-1", "team-1")
    assert get_params == ("rule-private", "user-1", "user-1", "team-1")


def test_rule_library_get_and_list_enforce_the_same_record_visibility(monkeypatch):
    from plugins.craft.craft_backend.capabilities import rule_library

    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute("""CREATE TABLE workmanship_know_craft_rules (
        gid TEXT, owner_user_gid TEXT, creator_gid TEXT, share_scope TEXT,
        applicable_scope TEXT, created_at TEXT
    )""")
    records = (
        ("owned", "user-1", "other", "private", '{"team_gid":"other-team"}', "1"),
        ("created", "other", "user-1", "private", '{"team_gid":"other-team"}', "2"),
        ("same-team", "other", "other", "team", '{"team_gid":"team-1"}', "3"),
        ("global", "other", "other", "global", '{"team_gid":"other-team"}', "4"),
        ("other-team", "other", "other", "team", '{"team_gid":"other-team"}', "5"),
        ("private", "other", "other", "private", '{"team_gid":"team-1"}', "6"),
    )
    database.executemany("INSERT INTO workmanship_know_craft_rules VALUES (?, ?, ?, ?, ?, ?)", records)

    class Cursor:
        def __init__(self):
            self.cursor = database.cursor()

        def __enter__(self): return self
        def __exit__(self, *_): self.cursor.close()
        def execute(self, sql, params=()):
            sql = sql.replace("JSON_UNQUOTE(JSON_EXTRACT(applicable_scope, '$.team_gid'))", "json_extract(applicable_scope, '$.team_gid')")
            self.cursor.execute(sql.replace("%s", "?"), params)
        def fetchone(self): return self.cursor.fetchone()
        def fetchall(self): return self.cursor.fetchall()

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(rule_library, "get_conn", lambda: Connection())
    context = CapabilityContext(user_gid="user-1", team_gid="team-1")
    try:
        listed = rule_library.read_rule_library({"operation": "list", "limit": 10}, context).data["data"]
        visible = {record["gid"] for record in listed}
        assert visible == {"owned", "created", "same-team", "global"}

        for gid in visible:
            result = rule_library.read_rule_library({"operation": "get", "gid": gid}, context)
            assert result.data["data"]["gid"] == gid

        for gid in ("other-team", "private"):
            with pytest.raises(ValueError, match="^rule not found$"):
                rule_library.read_rule_library({"operation": "get", "gid": gid}, context)
    finally:
        database.close()


def test_rule_library_get_and_list_outputs_match_both_registered_contracts():
    from backend.capabilities.validation_next import validate_payload
    from plugins.craft.craft_backend.capabilities.contracts import output_schema_for
    from plugins.craft.craft_backend.capabilities.provider import descriptor_for
    from plugins.craft.craft_backend.capabilities.rule_library import register_rule_library_capabilities

    class Registry:
        def __init__(self):
            self.specs = {}

        def register(self, spec, handler):
            self.specs[spec.id] = spec

    registry = Registry()
    register_rule_library_capabilities(registry)
    outputs = (
        {"success": True, "data": {"gid": "rule-1", "rule_reference": {"rule_gid": "rule-1"}}},
        {"success": True, "data": [{"gid": "rule-1"}]},
    )
    spec = registry.specs["craft.rule.library.read"]
    for schema in (spec.output_schema, output_schema_for("craft.rule.library.read", 1),
                   descriptor_for(spec).output_schema):
        for output in outputs:
            validate_payload(schema, output, label="output")
        for invalid in ({"success": True, "data": "rule-1"},
                        {"success": True, "data": [{}] * 501},
                        {"success": True, "data": {"gid": "rule-1", "unreviewed_field": "secret"}},
                        {"success": True, "data": [{"gid": "rule-1", "unreviewed_field": "secret"}]}):
            with pytest.raises(ValueError):
                validate_payload(schema, invalid, label="output")
