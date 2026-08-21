from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_version_freeze_change import apply_bop_version_freeze_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/versions.py")


def test_freeze_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.version.freeze.change.apply"') == 1
    assert "def _legacy_freeze_version" in source
    assert "def _legacy_unfreeze_version" in source


def test_freeze_change_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_version_freeze_change({"operation": "snapshot", "version_gid": "v1"}, object())


def test_freeze_change_validates_version_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_version_freeze_change({"operation": "freeze"}, object())
