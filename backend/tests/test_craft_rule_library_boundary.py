from __future__ import annotations

import ast
import json
import hashlib
from pathlib import Path

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
                self.current = dict(stored) if stored and params == ("rule-1",) else None
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
