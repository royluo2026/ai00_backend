from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_checkpoint_change import apply_bop_checkpoint_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_checkpoint_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.checkpoint.change.apply"') == 1
    assert "def _legacy_create_checkpoint" in source


def test_checkpoint_validates_identifiers_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_checkpoint_change({"operation": "create", "line_gid": "l1"}, object())


def test_checkpoint_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be create"):
        apply_bop_checkpoint_change({"operation": "rollback", "version_gid": "v1", "line_gid": "l1"}, object())
