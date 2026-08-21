from __future__ import annotations

import base64
from types import SimpleNamespace

from plugins.craft.craft_backend.capabilities.data_exchange import export_data


def test_excel_export_is_bounded_and_returns_xlsx_payload() -> None:
    result = export_data(
        {
            "operation": "excel",
            "template_config": {"columns": [{"key": "name", "label": "名称"}]},
            "rows": [{"name": "工序"}],
            "filename": "bop.xlsx",
        },
        SimpleNamespace(user_gid="u1"),
    )
    assert result["filename"] == "bop.xlsx"
    assert base64.b64decode(result["file_b64"]).startswith(b"PK")


def test_diff_report_export_returns_bounded_xlsx_payload() -> None:
    result = export_data(
        {
            "operation": "diff_report",
            "columns": [{"key": "name", "label": "名称"}],
            "diff_rows": [{"_diffStatus": "modified", "_rowA": {"name": "旧"}, "_rowB": {"name": "新"}, "_changedFields": ["name"]}],
        },
        SimpleNamespace(user_gid="u1"),
    )
    assert result["filename"].startswith("diff_report_")
    assert base64.b64decode(result["file_b64"]).startswith(b"PK")
