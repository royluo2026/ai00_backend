"""Gateway boundary tests for BOP lifecycle reads."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import lifecycle


def test_lifecycle_read_routes_are_gateway_bound():
    for name in ("get_lifecycle_history", "list_checkpoints", "get_line_history", "get_operation_log"):
        route = getattr(lifecycle, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.bop.lifecycle.read" in inspect.getsource(route)
    tree = ast.parse(Path(lifecycle.__file__).read_text(encoding="utf-8"))
    names = {"get_lifecycle_history", "list_checkpoints", "get_line_history", "get_operation_log"}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names:
            assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
