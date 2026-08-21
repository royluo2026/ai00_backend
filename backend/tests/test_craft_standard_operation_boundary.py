from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/std_op.py"


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
