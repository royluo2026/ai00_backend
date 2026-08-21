from __future__ import annotations

import ast
from pathlib import Path


ROUTER = Path("plugins/craft/craft_backend/routers/gbop.py")


def test_station_autolink_preview_route_uses_read_capability_gateway() -> None:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    route = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "station_autolink_preview"
    )
    assert any(
        isinstance(node, ast.Constant)
        and node.value == "craft.gbop.station_autolink.preview"
        for node in ast.walk(route)
    )


def test_station_autolink_preview_provider_contract_is_bounded() -> None:
    from plugins.craft.craft_backend.capabilities.station_autolink_preview import (
        OPERATIONS,
    )

    assert OPERATIONS == ("preview",)
