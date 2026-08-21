from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.gbop_import_tc_change import apply_gbop_import_tc_change


ROUTER = Path("plugins/craft/craft_backend/routers/gbop.py")


def test_gbop_tc_import_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.gbop.import.tc.change.apply"') == 1
    assert "async def _legacy_import_tc_excel" in source


def test_gbop_tc_import_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be import_tc_excel"):
        import asyncio
        asyncio.run(apply_gbop_import_tc_change({"operation": "delete", "version_gid": "v1"}, object()))
