"""Gateway boundary tests for legacy BOP version reads."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import versions


def test_legacy_version_read_routes_are_gateway_bound():
    for name in ("get_layout_config", "get_bop_tree", "get_station_part_map"):
        route = getattr(versions, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.bop.version.legacy_read" in inspect.getsource(route)
    tree = ast.parse(Path(versions.__file__).read_text(encoding="utf-8"))
    names = {"get_layout_config", "get_bop_tree", "get_station_part_map"}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names:
            assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
