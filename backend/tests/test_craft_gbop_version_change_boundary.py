from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.gbop_version_change import apply_gbop_version_change


ROUTER = Path("plugins/craft/craft_backend/routers/gbop.py")


def test_gbop_version_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.gbop.version.change.apply"') == 1
    for name in ("create_version", "update_version", "freeze_version", "archive_family", "unarchive_family", "fork_version"):
        assert f"def _legacy_{name}" in source


def test_gbop_version_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_gbop_version_change({"operation": "delete"}, object())
