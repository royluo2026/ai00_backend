"""Gateway boundary tests for legacy GBOP read routes."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import gbop


def test_legacy_gbop_read_routes_are_gateway_bound():
    for name in ("gbop_match_preview", "list_pbom_versions"):
        route = getattr(gbop, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.bop.gbop.legacy_read" in inspect.getsource(route)
    tree = ast.parse(Path(gbop.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"gbop_match_preview", "list_pbom_versions"}:
            assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))


def test_legacy_gbop_read_operations_are_declared():
    from plugins.craft.craft_backend.capabilities.bop_gbop_legacy_read import OPERATIONS

    assert set(OPERATIONS) == {"match_preview", "list_pbom_versions"}
