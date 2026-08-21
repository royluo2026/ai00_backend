from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "plugins/knowledge/knowledge_backend/api/knowledge_entries_legacy.py"
HUB_SOURCE = ROOT / "plugins/knowledge/knowledge_backend/api/knowledge_hub_legacy.py"


def _function(name: str):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name)


def _hub_function(name: str):
    tree = ast.parse(HUB_SOURCE.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name)


def test_knowledge_entry_writes_use_gateway_capability():
    for name in ("create_knowledge_entry", "update_knowledge_entry", "delete_knowledge_entry"):
        function = _function(name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert "_invoke_knowledge" in names
        assert "knowledge.entry.change.apply" in literals
        assert "get_conn" not in names
        assert "cur" not in names


def test_knowledge_entry_change_schema_carries_legacy_fields():
    from plugins.knowledge.knowledge_backend.capabilities.reviewed import SCHEMAS

    properties = SCHEMAS["knowledge.entry.change.apply"]["properties"]["arguments"]["properties"]
    assert {"list_gid", "source_gid", "source_label", "maintainer_gid", "attachments", "content_ref", "related_part_nos", "related_operation_gids", "context_class_gid"} <= set(properties)
    updates = properties["updates"]["properties"]
    assert {"list_gid", "source_gid", "attachments", "content_ref", "context_class_gid"} <= set(updates)


def test_unsupported_vector_search_route_is_explicitly_retired():
    function = _function("vector_search_knowledge")
    assert any(
        isinstance(decorator, ast.Call)
        and any(
            keyword.arg == "status_code"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == 410
            for keyword in decorator.keywords
        )
        for decorator in function.decorator_list
    )


def test_hub_personalization_routes_use_gateway_capabilities():
    expected = {
        "toggle_favorite": ("knowledge.personalization.change.apply", "favorites.toggle"),
        "record_recent": ("knowledge.personalization.change.apply", "recent.record"),
        "list_favorites": ("knowledge.personalization.read", "favorites.list"),
        "list_recent": ("knowledge.personalization.read", "recent.list"),
    }
    for name, literals_expected in expected.items():
        function = _hub_function(name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert isinstance(function, ast.AsyncFunctionDef)
        assert "_invoke" in names
        assert set(literals_expected) <= literals
        assert "cur" not in names


def test_personalization_read_accepts_bounded_limit():
    from plugins.knowledge.knowledge_backend.capabilities.reviewed import SCHEMAS

    props = SCHEMAS["knowledge.personalization.read"]["properties"]["arguments"]["properties"]
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 200


def test_hub_folder_routes_use_governed_capabilities():
    hub = HUB_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(hub)
    for name in ("list_folders", "create_folder", "patch_folder", "delete_folder"):
        function = next(node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        assert isinstance(function, ast.AsyncFunctionDef)
        assert "_invoke" in names
        assert "get_conn" not in names


def test_hub_item_routes_use_governed_capabilities():
    hub = HUB_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(hub)
    for name in ("list_items", "get_item", "create_item", "patch_item", "get_item_history", "delete_item"):
        function = next(node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        assert isinstance(function, ast.AsyncFunctionDef)
        assert "_invoke" in names
        assert "get_conn" not in names
