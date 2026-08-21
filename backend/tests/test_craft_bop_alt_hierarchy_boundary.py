"""Gateway boundary tests for BOP alternative hierarchy."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import entries


def test_alt_hierarchy_is_gateway_bound_and_literal():
    route = entries.get_alt_hier
    assert inspect.iscoroutinefunction(route)
    assert "craft.bop.alt_hierarchy.read" in inspect.getsource(route)
    tree = ast.parse(Path(entries.__file__).read_text(encoding="utf-8"))
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.AsyncFunctionDef) and item.name == "get_alt_hier")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
