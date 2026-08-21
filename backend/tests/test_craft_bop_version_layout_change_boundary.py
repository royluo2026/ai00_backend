from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_version_layout_change import apply_bop_version_layout_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/versions.py")


def test_layout_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.version.layout.change.apply"') == 1
    assert "def _legacy_put_layout_config" in source


def test_layout_change_validates_config_before_io() -> None:
    with pytest.raises(ValueError, match="config must be an object"):
        apply_bop_version_layout_change({"version_gid": "v1", "config": []}, object())
