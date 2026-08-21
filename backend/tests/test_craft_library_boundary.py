from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/craft_library.py"


def _function(name: str):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name)


def test_library_read_routes_delegate_to_gateway():
    for name in ("list_tools", "list_equipments", "list_fixtures", "list_fasteners", "list_part_names"):
        function = _function(name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert isinstance(function, ast.AsyncFunctionDef)
        assert "_invoke_library" in names
        assert any(value.endswith(".list") for value in literals)
        assert "get_conn" not in names

    helper = _function("_invoke_library")
    helper_literals = {node.value for node in ast.walk(helper) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "craft.library.read" in helper_literals


def test_library_read_capability_is_bounded_and_closed():
    from plugins.craft.craft_backend.capabilities.library_read import _OPERATIONS, read_library

    assert _OPERATIONS == ("tools.list", "equipments.list", "fixtures.list", "fasteners.list", "part_names.list")
    try:
        read_library({"operation": "unknown"}, None)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown Craft library operation must be rejected")
