from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_checkpoint_rollback import apply_bop_checkpoint_rollback


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_checkpoint_rollback_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.checkpoint.rollback.apply"') == 1
    assert "def _legacy_rollback_to_checkpoint" in source


def test_checkpoint_rollback_validates_identifiers_before_io() -> None:
    with pytest.raises(ValueError, match="checkpoint_gid is required"):
        apply_bop_checkpoint_rollback({"version_gid": "v1", "line_gid": "l1"}, object())


def test_checkpoint_rollback_validates_all_identifiers_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_checkpoint_rollback({"line_gid": "l1", "checkpoint_gid": "c1"}, object())
