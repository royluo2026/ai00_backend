from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/vpps_audit.py"


def test_vpps_audit_routes_are_gateway_adapters():
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    names = {node.name: node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))}
    for name in ("rule4_bulk_ignore", "list_operations", "get_rule4_ignores", "revert_operation"):
        node = names[name]
        assert isinstance(node, ast.AsyncFunctionDef)
        identifiers = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        assert "_invoke_vpps_audit" in identifiers
        assert "get_conn" not in identifiers


def test_vpps_audit_operations_are_closed():
    from plugins.craft.craft_backend.capabilities.vpps_audit import CHANGE_OPERATIONS, READ_OPERATIONS

    assert READ_OPERATIONS == ("list", "rule4_ignores")
    assert CHANGE_OPERATIONS == ("rule4_bulk_ignore", "revert")
