"""Gateway boundary tests for the GBOP navigation compatibility routes."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.capabilities.gbop_navigation import OPERATIONS
from plugins.craft.craft_backend.routers import gbop


def test_navigation_capability_declares_bounded_operations():
    assert OPERATIONS == ("link_summary", "auto_link_status")


def test_navigation_routes_are_async_gateway_adapters_without_sql():
    for name in ("gbop_nav_link_summary", "gbop_vpps_auto_link_status"):
        route = getattr(gbop, name)
        assert inspect.iscoroutinefunction(route)
        source = inspect.getsource(route)
        assert "craft.gbop.navigation.read" in source
        assert "_invoke_gbop_navigation" in source

    tree = ast.parse(Path(gbop.__file__).read_text(encoding="utf-8"))
    route_names = {"gbop_nav_link_summary", "gbop_vpps_auto_link_status"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in route_names:
            assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
