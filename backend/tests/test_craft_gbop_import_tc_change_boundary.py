from pathlib import Path
import asyncio
import base64

import pytest
from fastapi import HTTPException

from plugins.craft.craft_backend.capabilities.gbop_import_tc_change import apply_gbop_import_tc_change
from plugins.craft.craft_backend.routers.gbop import _required_excel_columns
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext


ROUTER = Path("plugins/craft/craft_backend/routers/gbop.py")


def test_gbop_tc_import_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.gbop.import.tc.change.apply"') == 1
    assert "async def _legacy_import_tc_excel" in source


def test_gbop_tc_import_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be import_tc_excel"):
        asyncio.run(apply_gbop_import_tc_change({"operation": "delete", "version_gid": "v1"}, object()))


def test_gbop_tc_import_requires_sheet_1_matching_columns() -> None:
    with pytest.raises(Exception) as exc_info:
        _required_excel_columns(
            "1",
            ["零组件名称", "VPPS"],
            ("零组件类型", "零组件名称", "BOM 行", "VPPS", "父级"),
        )

    assert getattr(exc_info.value, "status_code", None) == 400
    assert "零组件类型、BOM 行、父级" in str(getattr(exc_info.value, "detail", exc_info.value))


def test_gbop_tc_import_requires_sheet_2_auto_match_columns() -> None:
    indexes = _required_excel_columns(
        "2",
        ["VPPS", "工序VPPS", "操作VPPS", "标记"],
        ("VPPS", "工序VPPS", "操作VPPS", "标记"),
    )

    assert indexes == {"VPPS": 0, "工序VPPS": 1, "操作VPPS": 2, "标记": 3}


def test_gbop_tc_import_surfaces_missing_columns_as_invalid_input(monkeypatch) -> None:
    from plugins.craft.craft_backend.routers import gbop

    async def reject_columns(*_args, **_kwargs):
        raise HTTPException(400, "Sheet 1 缺少必需列：零组件类型")

    monkeypatch.setattr(gbop, "_legacy_import_tc_excel", reject_columns)
    payload = {
        "operation": "import_tc_excel",
        "version_gid": "v1",
        "content_b64": base64.b64encode(b"workbook").decode("ascii"),
    }
    with pytest.raises(CapabilityBusinessError) as exc_info:
        asyncio.run(apply_gbop_import_tc_change(payload, CapabilityContext(user_gid="u1")))

    assert exc_info.value.code == "invalid_input"
    assert "零组件类型" in exc_info.value.message


def test_gbop_tc_import_preserves_actor_team(monkeypatch) -> None:
    from plugins.craft.craft_backend.routers import gbop

    captured = {}

    async def accept_import(_version_gid, _upload, current_user):
        captured.update(current_user)
        return {"data": {"processes_created": 1}}

    monkeypatch.setattr(gbop, "_legacy_import_tc_excel", accept_import)
    payload = {
        "operation": "import_tc_excel",
        "version_gid": "v1",
        "content_b64": base64.b64encode(b"workbook").decode("ascii"),
    }
    asyncio.run(
        apply_gbop_import_tc_change(
            payload,
            CapabilityContext(user_gid="u1", team_gid="team-1"),
        )
    )

    assert captured["team_id"] == "team-1"
