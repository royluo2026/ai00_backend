"""Gateway boundary tests for legacy BOP entry read routes."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from plugins.craft.craft_backend.routers._bop import entries


ROUTES = (
    "auto_link_preview",
    "get_link_summary",
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
        "link_summary",
        "resolve_gids",
        "pbom_search",
        "pbom_snapshots",
        "project_bop_lines",
        "line_operations",
        "version_history",
        "entry_history",
        "version_entries",
    }


def test_relation_routes_use_atomic_read_capabilities():
    assert "craft.bop.entry.relation.list" in inspect.getsource(entries.list_entry_links)
    assert "craft.bop.linked_entity.detail.get" in inspect.getsource(entries.get_entity_detail)
    assert "craft.bop.entry.legacy_read" not in inspect.getsource(entries.list_entry_links)
    assert "craft.bop.entry.legacy_read" not in inspect.getsource(entries.get_entity_detail)


def test_version_entries_rejects_unbounded_pages():
    from plugins.craft.craft_backend.capabilities.bop_entry_legacy_read import read_bop_entry_legacy

    with pytest.raises(ValueError, match="between 1 and 100"):
        read_bop_entry_legacy({"operation": "version_entries", "version_gid": "v1", "limit": 101}, None)


def test_version_entries_rejects_negative_offset():
    from plugins.craft.craft_backend.capabilities.bop_entry_legacy_read import read_bop_entry_legacy

    with pytest.raises(ValueError, match="non-negative"):
        read_bop_entry_legacy({"operation": "version_entries", "version_gid": "v1", "offset": -1}, None)
