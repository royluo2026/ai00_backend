from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_lifecycle_stats_refresh import apply_bop_lifecycle_stats_refresh


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_stats_refresh_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.stats.refresh.apply"') == 1
    assert "def _legacy_refresh_stats" in source


def test_stats_refresh_validates_version_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_lifecycle_stats_refresh({}, object())
