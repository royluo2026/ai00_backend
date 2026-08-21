from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.gbop_import_change import apply_gbop_import_change


ROUTER = Path("plugins/craft/craft_backend/routers/gbop.py")


def test_gbop_import_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.gbop.import.change.apply"') == 1
    assert "def _legacy_import_vpps_parts" in source
    assert "def _legacy_import_entries" in source


def test_gbop_import_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_gbop_import_change({"operation": "delete", "version_gid": "v1"}, object())
