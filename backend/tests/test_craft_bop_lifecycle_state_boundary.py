"""Gateway boundary tests for aggregate BOP lifecycle state."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import lifecycle


def test_lifecycle_state_route_is_gateway_bound():
    route = lifecycle.get_lifecycle
    assert inspect.iscoroutinefunction(route)
    assert "craft.bop.lifecycle.state.read" in inspect.getsource(route)
    tree = ast.parse(Path(lifecycle.__file__).read_text(encoding="utf-8"))
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.AsyncFunctionDef) and item.name == "get_lifecycle")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
