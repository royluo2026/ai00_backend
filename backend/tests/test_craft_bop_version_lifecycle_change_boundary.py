from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_version_lifecycle_change import apply_bop_version_lifecycle_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/versions.py")


def test_version_lifecycle_routes_share_one_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.version.lifecycle.change.apply"') == 1
    for legacy in ("_legacy_publish_version", "_legacy_archive_family", "_legacy_unarchive_family"):
        assert f"def {legacy}" in source


def test_version_lifecycle_rejects_unknown_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_version_lifecycle_change({"operation": "freeze"}, object())


def test_version_lifecycle_requires_operation_identifier_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_version_lifecycle_change({"operation": "publish"}, object())
