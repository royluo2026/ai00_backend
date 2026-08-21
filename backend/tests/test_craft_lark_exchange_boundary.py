from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.lark_exchange import read_lark_data, write_lark_data


ROUTER = Path("plugins/craft/craft_backend/routers/import_export.py")


def test_lark_routes_use_governed_read_and_write_capabilities() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.data_exchange.lark.read"') == 1
    assert source.count('capability_id="craft.data_exchange.lark.write"') == 1
    for legacy in ("_legacy_lark_sheets_read", "_legacy_lark_sheets_write", "_legacy_lark_bitable_read", "_legacy_lark_bitable_write"):
        assert f"async def {legacy}" in source


def test_lark_read_rejects_unknown_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        read_lark_data({"operation": "sheets.delete"}, object())


def test_lark_write_validates_values_before_io() -> None:
    with pytest.raises(ValueError, match="values must be a non-empty array"):
        write_lark_data({"operation": "sheets.write", "user_access_token": "t", "spreadsheet_token": "s", "sheet_id": "Sheet1", "values": []}, object())
