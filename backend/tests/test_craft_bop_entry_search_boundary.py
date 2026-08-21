"""Gateway boundary tests for BOP entry search."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import entries


def test_entry_search_is_gateway_bound_and_literal():
    route = entries.search_entries
    assert inspect.iscoroutinefunction(route)
    assert "craft.bop.entry.search" in inspect.getsource(route)
    tree = ast.parse(Path(entries.__file__).read_text(encoding="utf-8"))
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.AsyncFunctionDef) and item.name == "search_entries")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
