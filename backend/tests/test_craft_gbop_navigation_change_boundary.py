"""Gateway boundary tests for GBOP navigation mutations."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.capabilities.gbop_navigation_change import OPERATIONS
from plugins.craft.craft_backend.routers import gbop


def test_navigation_change_operations_are_bounded():
    assert OPERATIONS == ("confirm", "auto_link")


def test_navigation_change_routes_are_gateway_adapters_without_sql():
    for name in ("gbop_vpps_auto_link_confirm", "gbop_vpps_auto_link"):
        route = getattr(gbop, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.gbop.navigation.change.apply" in inspect.getsource(route)
    tree = ast.parse(Path(gbop.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"gbop_vpps_auto_link_confirm", "gbop_vpps_auto_link"}:
            assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
