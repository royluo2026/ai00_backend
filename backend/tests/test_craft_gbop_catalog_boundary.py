from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/gbop.py"


def test_gbop_catalog_read_routes_use_gateway():
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))}
    for name in ("list_entries", "list_processes", "list_operations", "get_entry_links"):
        node = functions[name]
        assert isinstance(node, ast.AsyncFunctionDef)
        identifiers = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        assert "_invoke_gbop_catalog" in identifiers
        assert "get_conn" not in identifiers


def test_gbop_catalog_operations_are_closed():
    from plugins.craft.craft_backend.capabilities.gbop_catalog import OPERATIONS

    assert OPERATIONS == ("entries.list", "processes.list", "operations.list", "entry_links.list")
