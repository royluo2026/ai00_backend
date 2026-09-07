import asyncio
from pathlib import Path
from types import SimpleNamespace


ROUTER = Path("plugins/craft/craft_backend/routers/import_export.py")


def test_export_routes_use_data_exchange_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.data_exchange.export"') == 1
    for route in ("/export/excel", "/export/diff-report", "/export/diff-lark-sheet"):
        assert route in source
    assert "def _legacy_export_excel" in source
    assert "def _legacy_export_diff_report" in source
    assert "async def _legacy_export_diff_lark_sheet" in source


def test_parse_excel_route_uses_bop_import_preview_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert 'capability_id="craft.bop.import.preview"' in source
    assert "def _legacy_parse_excel" in source


def test_parse_excel_adds_the_direct_gateway_preview_payload(monkeypatch) -> None:
    from plugins.craft.craft_backend.routers import import_export

    parsed = {"success": True, "data": {"headers": ["工序代码"], "rows": [["OP-1"]], "warnings": []}}
    preview = {"import_preview_gid": "preview-1", "summary": {"entries": 1}}

    async def invoke(*_args, **_kwargs):
        return SimpleNamespace(ok=True, data=preview, error=None)

    monkeypatch.setattr(import_export, "_legacy_parse_excel", lambda *_args: parsed)
    monkeypatch.setattr(import_export, "invoke_compatibility", invoke)
    monkeypatch.setattr(import_export, "build_web_compatibility_envelope", lambda *_args, **_kwargs: object())

    result = asyncio.run(import_export.parse_excel(
        import_export.ParseExcelBody(file_b64="AA==", filename="operations.xlsx", module="bop"),
        SimpleNamespace(headers={}),
        user={"gid": "user-1"},
        principal=object(),
        gateway=object(),
    ))

    assert result["data"]["import_preview"] == preview


def test_parse_excel_does_not_run_bop_preview_for_gbop_library(monkeypatch) -> None:
    from plugins.craft.craft_backend.routers import import_export

    parsed = {"success": True, "data": {"headers": ["零组件类型"], "rows": [["总装工序"]], "warnings": []}}

    async def unexpected_invoke(*_args, **_kwargs):
        raise AssertionError("GBOP library parsing must not invoke BOP preview")

    monkeypatch.setattr(import_export, "_legacy_parse_excel", lambda *_args: parsed)
    monkeypatch.setattr(import_export, "invoke_compatibility", unexpected_invoke)

    result = asyncio.run(import_export.parse_excel(
        import_export.ParseExcelBody(file_b64="AA==", filename="gbop.xlsx", module="std_op_lib"),
        SimpleNamespace(headers={}),
        user={"gid": "user-1"},
        principal=object(),
        gateway=object(),
    ))

    assert result == parsed
