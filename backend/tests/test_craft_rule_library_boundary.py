from __future__ import annotations

import ast
from pathlib import Path


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
