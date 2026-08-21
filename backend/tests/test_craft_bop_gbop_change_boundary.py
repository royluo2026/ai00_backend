from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_gbop_change import apply_bop_gbop_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/gbop.py")


def test_gbop_change_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.gbop.change.apply"') == 1
    assert "def _legacy_gbop_match_confirm" in source
    assert "def _legacy_gbop_auto_link" in source


def test_gbop_change_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_gbop_change({"operation": "delete"}, object())
