"""Gateway boundary tests for legacy BOP entry read routes."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import entries


ROUTES = (
    "auto_link_preview",
    "list_entry_links",
    "get_link_summary",
    "get_entity_detail",
    "resolve_gids",
    "search_pbom_parts",
    "list_pbom_snapshots",
    "get_line_operations",
    "get_version_history",
    "get_entry_history",
)


def test_legacy_entry_read_routes_are_gateway_bound():
    for name in ROUTES:
        route = getattr(entries, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.bop.entry.legacy_read" in inspect.getsource(route)

    tree = ast.parse(Path(entries.__file__).read_text(encoding="utf-8"))
    names = set(ROUTES)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names:
            assert not any(
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "get_conn"
                for item in ast.walk(node)
            )


def test_legacy_entry_read_capability_declared():
    from plugins.craft.craft_backend.capabilities.bop_entry_legacy_read import OPERATIONS

    assert set(OPERATIONS) == {
        "auto_link_preview",
        "entry_links",
        "link_summary",
        "entity_detail",
        "resolve_gids",
        "pbom_search",
        "pbom_snapshots",
        "project_bop_lines",
        "line_operations",
        "version_history",
        "entry_history",
    }
