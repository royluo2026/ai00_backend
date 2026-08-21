"""Gateway boundary tests for PBOM/BOP lifecycle reads."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import lifecycle


def test_pbom_lifecycle_read_routes_are_gateway_bound():
    for name in ("get_pbom_link_stats", "get_pbom_diff_queue"):
        route = getattr(lifecycle, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.bop.pbom_lifecycle.read" in inspect.getsource(route)
    tree = ast.parse(Path(lifecycle.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"get_pbom_link_stats", "get_pbom_diff_queue"}:
            assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
