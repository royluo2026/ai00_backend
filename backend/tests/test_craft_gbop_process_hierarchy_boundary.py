"""Gateway boundary tests for the GBOP process hierarchy route."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.capabilities.gbop_process_hierarchy import read_gbop_process_hierarchy
from plugins.craft.craft_backend.routers import gbop


def test_process_hierarchy_provider_and_route_are_gateway_bound():
    assert callable(read_gbop_process_hierarchy)
    route = gbop.gbop_process_hierarchy
    assert inspect.iscoroutinefunction(route)
    source = inspect.getsource(route)
    assert "craft.gbop.process_hierarchy.read" in source
    assert "_invoke_gbop_process_hierarchy" in source
    tree = ast.parse(Path(gbop.__file__).read_text(encoding="utf-8"))
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.AsyncFunctionDef) and item.name == "gbop_process_hierarchy")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))
