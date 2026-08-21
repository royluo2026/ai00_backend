"""Gateway boundary test for the legacy staging read route."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import staging


def test_staging_read_route_is_gateway_bound():
    route = staging.list_staging
    assert inspect.iscoroutinefunction(route)
    assert "craft.bop.staging.read" in inspect.getsource(route)
    tree = ast.parse(Path(staging.__file__).read_text(encoding="utf-8"))
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.AsyncFunctionDef) and item.name == "list_staging")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))


def test_staging_read_capability_is_declared():
    from plugins.craft.craft_backend.capabilities.bop_staging_read import OPERATIONS

    assert OPERATIONS == ("list",)
