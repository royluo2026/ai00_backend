from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_lifecycle_stats_refresh import apply_bop_lifecycle_stats_refresh
from plugins.craft.craft_backend.routers._bop.lifecycle import _get_line_subtree_gids


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_stats_refresh_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.stats.refresh.apply"') == 1
    assert "def _legacy_refresh_stats" in source


def test_stats_refresh_validates_version_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_lifecycle_stats_refresh({}, object())


def test_line_subtree_uses_flat_hierarchy_query() -> None:
    class Cursor:
        def execute(self, sql, params):
            assert "WITH RECURSIVE" not in sql
            assert params == ("version-1",)

        def fetchall(self):
            return [
                {"gid": "line-1", "parent_gid": "root"},
                {"gid": "station-1", "parent_gid": "line-1"},
                {"gid": "operation-1", "parent_gid": "station-1"},
                {"gid": "line-2", "parent_gid": "root"},
            ]

    assert _get_line_subtree_gids(Cursor(), "version-1", "line-1") == [
        "line-1", "station-1", "operation-1",
    ]
