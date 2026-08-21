from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _function(name: str):
    source = (ROOT / "plugins/craft/craft_backend/routers/ebom.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    return next(node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name)


def test_pbom_snapshot_reads_use_gateway_capabilities():
    for name, capability in (
        ("list_snapshots", "craft.pbom.version.search"),
        ("get_snapshot", "craft.pbom.version.get"),
    ):
        function = _function(name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert "_invoke_pbom" in names
        assert capability in literals
        assert "get_conn" not in names
        assert "cur" not in names


def test_pbom_snapshot_create_uses_gateway_capability():
    function = _function("create_snapshot")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "_invoke_pbom" in names
    assert "craft.pbom.version.create" in literals
    assert "get_conn" not in names
    assert "cur" not in names


def test_pbom_version_contract_preserves_legacy_snapshot_metadata():
    from plugins.craft.craft_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS

    properties = INPUT_SCHEMAS["craft.pbom.version.create"]["properties"]
    assert {"project_gid", "name", "source_type"} <= set(properties)
    output_properties = OUTPUT_SCHEMAS["craft.pbom.version.get"]["properties"]
    assert {"name", "source_type", "created_at", "meta"} <= set(output_properties)


def test_pbom_parts_read_uses_bounded_part_search_capability():
    function = _function("list_parts")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "_invoke_pbom" in names
    assert "craft.pbom.part.search" in literals
    assert "get_conn" not in names
    assert "cur" not in names


def test_pbom_part_search_output_is_bounded_collection():
    from plugins.craft.craft_backend.capabilities.contracts import OUTPUT_SCHEMAS

    items = OUTPUT_SCHEMAS["craft.pbom.part.search"]["properties"]["items"]
    assert items["type"] == "array"
    assert items["maxItems"] == 500
