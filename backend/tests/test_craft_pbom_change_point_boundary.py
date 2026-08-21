from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "plugins/craft/craft_backend/routers/_bop/pbom.py"


def test_pbom_change_point_route_uses_gateway():
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "pbom_change_point")
    assert isinstance(node, ast.AsyncFunctionDef)
    identifiers = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
    assert "_invoke_pbom_change_point" in identifiers
    assert "get_conn" not in identifiers


def test_pbom_change_point_operation_is_bounded():
    from plugins.craft.craft_backend.capabilities.pbom_change_point import OPERATION

    assert OPERATION == "get"
