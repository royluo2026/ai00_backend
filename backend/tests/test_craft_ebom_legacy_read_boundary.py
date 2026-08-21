from __future__ import annotations

import ast
from pathlib import Path


ROUTER = Path("plugins/craft/craft_backend/routers/ebom.py")


def test_ebom_diff_route_uses_legacy_read_gateway_capability() -> None:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    route = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "diff_snapshots"
    )
    assert any(
        isinstance(node, ast.Constant)
        and node.value == "craft.ebom.legacy_read"
        for node in ast.walk(route)
    )


def test_ebom_legacy_read_provider_is_read_only_and_bounded() -> None:
    from plugins.craft.craft_backend.capabilities.ebom_legacy_read import OPERATIONS

    assert OPERATIONS == ("diff",)
