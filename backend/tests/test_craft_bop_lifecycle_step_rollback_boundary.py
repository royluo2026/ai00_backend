from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_lifecycle_step_rollback import apply_bop_lifecycle_step_rollback


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_step_rollback_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.step.rollback.apply"') == 1
    assert "def _legacy_undo_lifecycle_step" in source


def test_step_rollback_validates_step_before_io() -> None:
    with pytest.raises(ValueError, match="step_key must be one of"):
        apply_bop_lifecycle_step_rollback({"version_gid": "v1", "step_key": "unknown"}, object())


def test_step_rollback_validates_version_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_lifecycle_step_rollback({"step_key": "lines_added"}, object())
