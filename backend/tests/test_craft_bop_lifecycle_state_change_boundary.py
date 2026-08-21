from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_lifecycle_state_change import apply_bop_lifecycle_state_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_lifecycle_state_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.state.change.apply"') == 1
    assert "def _legacy_update_init_state" in source
    assert "def _legacy_confirm_phase" in source


def test_lifecycle_state_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_lifecycle_state_change({"operation": "rollback"}, object())


def test_lifecycle_state_validates_version_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_lifecycle_state_change({"operation": "phase.confirm"}, object())
