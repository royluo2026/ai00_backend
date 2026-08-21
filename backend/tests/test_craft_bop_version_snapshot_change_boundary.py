from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_version_snapshot_change import apply_bop_version_snapshot_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/versions.py")


def test_snapshot_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.version.snapshot.change.apply"') == 1
    assert "def _legacy_freeze_snapshot" in source
    assert "def _legacy_promote_version" in source


def test_snapshot_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_version_snapshot_change({"operation": "rollback", "version_gid": "v1"}, object())


def test_snapshot_validates_version_identifier_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_version_snapshot_change({"operation": "freeze_snapshot"}, object())
