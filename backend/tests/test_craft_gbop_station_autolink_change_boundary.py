from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.gbop_station_autolink_change import apply_gbop_station_autolink_change


ROUTER = Path("plugins/craft/craft_backend/routers/gbop.py")


def test_station_autolink_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.gbop.station_autolink.change.apply"') == 1
    assert "def _legacy_station_autolink" in source
    assert "def _legacy_station_autolink_undo" in source


def test_station_autolink_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_gbop_station_autolink_change({"operation": "preview", "bop_gid": "b1"}, object())
