from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/rule_engine.py"


def test_rule_engine_routes_use_gateway_boundary():
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))}
    for name in ("check_single_rule", "audit_bop_version"):
        node = functions[name]
        assert isinstance(node, ast.AsyncFunctionDef)
        assert "_invoke_rule_engine" in {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        assert "get_conn" not in {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def test_rule_engine_operation_is_closed():
    from plugins.craft.craft_backend.capabilities.rule_engine import OPERATIONS

    assert OPERATIONS == ("check", "audit")
