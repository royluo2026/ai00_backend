from pathlib import Path


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
