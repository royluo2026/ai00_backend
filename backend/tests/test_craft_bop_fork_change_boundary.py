from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_fork_change import apply_bop_fork_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/fork.py")


def test_fork_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.fork.change.apply"') == 1
    assert "def _legacy_fork_version" in source
    assert "def _legacy_smart_fork_version" in source
    assert "def _legacy_stage_advance" in source


def test_fork_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_fork_change({"operation": "delete", "source_version_gid": "v1"}, object())


def test_fork_validates_source_identifier_before_io() -> None:
    with pytest.raises(ValueError, match="source_version_gid is required"):
        apply_bop_fork_change({"operation": "fork"}, object())
