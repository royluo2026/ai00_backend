"""The Bitable index is an authoritative, complete one-way catalog snapshot."""
import pytest

from plugins.knowledge.knowledge_backend.feishu_catalog import (
    catalog_row,
    fetch_all_records,
    parse_bitable_url,
    parse_catalog_url,
    sheet_catalog_records,
    reconcile_catalog_rows,
)


def test_bitable_url_requires_unambiguous_app_and_table_ids():
    assert parse_bitable_url("https://example.feishu.cn/base/bascn123?table=tbl456") == ("bascn123", "tbl456")
    with pytest.raises(ValueError): parse_bitable_url("https://example.feishu.cn/base/bascn123")
    with pytest.raises(ValueError): parse_bitable_url("https://evil.example/base/bascn123?table=tbl456")
    with pytest.raises(ValueError): parse_bitable_url("https://example.feishu.cn/base/bascn123?table=tbl1&table=tbl2")


def test_wiki_sheet_catalog_url_and_total_sheet_rows():
    assert parse_catalog_url("https://li.feishu.cn/wiki/SEqFwOafKi0zeJkOckvciGXbngh") == (
        "wiki_sheet", "SEqFwOafKi0zeJkOckvciGXbngh", None,
    )
    assert parse_catalog_url("https://li.feishu.cn/sheets/sht123?sheet=abc123") == (
        "sheet", "sht123", "abc123",
    )
    values = [["名称", "飞书文档"], ["BOP 指南", "https://li.feishu.cn/docx/abc123"],
              ["另一个", "https://li.feishu.cn/wiki/xyz123"]]
    records = sheet_catalog_records(values)
    assert [record["record_id"] for record in records] == ["sheet:abc123", "sheet:xyz123"]
    assert catalog_row(records[0])["document_token"] == "abc123"


def test_sheet_catalog_rejects_missing_document_column():
    with pytest.raises(ValueError, match="文档链接"):
        sheet_catalog_records([["名称", "备注"], ["A", "无"]])


def test_sheet_catalog_infers_a_custom_link_column_without_guessing_multiple_columns():
    records = sheet_catalog_records([["文档标题", "知识文档地址"], ["BOP", "https://li.feishu.cn/docx/abc123"]])
    assert catalog_row(records[0])["title"] == "BOP"
    assert catalog_row(records[0])["document_token"] == "abc123"


def test_sheet_catalog_reads_rich_link_and_refuses_an_unreadable_snapshot():
    records = sheet_catalog_records([["名称", "文档链接"], ["BOP", {"text": "打开", "link": "https://li.feishu.cn/wiki/abc123"}]])
    assert catalog_row(records[0])["document_token"] == "abc123"
    with pytest.raises(ValueError, match="保护现有清单"):
        sheet_catalog_records([["名称", "文档链接"], ["BOP", "打开"]])


def test_fetch_all_records_consumes_every_page_and_rejects_partial_results():
    calls = []
    pages = [
        {"items": [{"record_id": f"rec{i}", "fields": {}} for i in range(50)], "has_more": True, "page_token": "next"},
        {"items": [{"record_id": "rec50", "fields": {}}], "has_more": False},
    ]
    def fetch(page_token):
        calls.append(page_token)
        return pages.pop(0)
    assert len(fetch_all_records(fetch)) == 51
    assert calls == [None, "next"]
    with pytest.raises(ValueError, match="incomplete"):
        fetch_all_records(lambda _token: {"items": [], "has_more": True})


def test_catalog_row_retains_feishu_record_id_and_extracts_doc_link():
    row = catalog_row({"record_id": "rec1", "fields": {
        "名称": "BOP 指南", "飞书文档": [{"text": "打开", "link": "https://example.feishu.cn/docx/abc123"}],
    }})
    assert row == {"record_id": "rec1", "title": "BOP 指南", "document_url": "https://example.feishu.cn/docx/abc123", "document_token": "abc123", "error": None}


def test_catalog_row_reports_missing_or_invalid_links():
    assert catalog_row({"record_id": "r1", "fields": {"名称": "A"}})["error"] == "document_link_missing"
    assert catalog_row({"record_id": "r2", "fields": {"名称": "A", "飞书文档": "https://evil.example/docx/x"}})["error"] == "document_link_invalid"


def test_reconcile_preserves_record_gid_but_replaces_source_when_link_changes():
    existing = {"r1": {"gid": "catalog_1", "source_gid": "source_A", "document_token": "old"}}
    incoming = [{"record_id": "r1", "title": "BOP", "document_url": "https://example.feishu.cn/docx/new", "document_token": "new", "error": None}]
    rows, retired = reconcile_catalog_rows(incoming, existing, lambda kind: f"new_{kind}")
    assert rows[0]["gid"] == "catalog_1"
    assert rows[0]["source_gid"] == "new_source"
    assert retired == ["source_A"]


def test_reconcile_retires_missing_rows_and_marks_duplicate_documents():
    row = {"title": "BOP", "document_url": "https://example.feishu.cn/docx/same", "document_token": "same", "error": None}
    rows, retired = reconcile_catalog_rows([
        {**row, "record_id": "r1"}, {**row, "record_id": "r2"},
    ], {"r3": {"gid": "catalog_3", "source_gid": "source_3", "document_token": "old"}}, lambda kind: f"new_{kind}")
    assert all(item["error"] == "document_link_duplicate" for item in rows)
    assert "source_3" in retired


def test_only_superadmin_can_change_or_sync_catalog():
    from backend.capabilities.models_next import CapabilityContext
    from plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next import save_catalog_config, sync_catalog
    from unittest.mock import patch
    context = CapabilityContext(user_gid="member", team_gid="team_1")
    with patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={
        "gid": "member", "team_id": "team_1", "system_role": "member", "is_active": True,
    }):
        with pytest.raises(PermissionError):
            save_catalog_config({"url": "https://example.feishu.cn/base/bascn123?table=tbl456"}, context)
        with pytest.raises(PermissionError):
            sync_catalog({}, context)


def test_failed_second_page_does_not_open_catalog_write_transaction():
    from backend.capabilities.models_next import CapabilityContext
    from plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next import sync_catalog
    from unittest.mock import patch

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, _params):
            assert sql.startswith("SELECT source_url,app_token,table_id")
        def fetchone(self): return {"source_url": "https://example.feishu.cn/base/bascn123?table=tbl456", "app_token": "bascn123", "table_id": "tbl456"}
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    calls = []
    def page(_app, _table, token):
        calls.append(token)
        if token:
            raise RuntimeError("Feishu page unavailable")
        return {"items": [{"record_id": "r1", "fields": {}}], "has_more": True, "page_token": "next"}
    with patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={
        "gid": "admin", "team_id": "team_1", "system_role": "super_admin", "is_active": True,
    }), patch("plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next.get_knowledge_conn", return_value=Connection()) as connect, \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next.feishu_service.list_bitable_records", side_effect=page):
        with pytest.raises(RuntimeError, match="unavailable"):
            sync_catalog({}, CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert calls == [None, "next"]
    assert connect.call_count == 1


def test_wiki_sheet_link_saves_without_requiring_feishu_read_permission():
    from backend.capabilities.models_next import CapabilityContext
    from plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next import save_catalog_config
    from unittest.mock import patch

    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): statements.append((sql, params))
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): pass
    with patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={
        "gid": "admin", "team_id": "team_1", "system_role": "super_admin", "is_active": True,
    }), patch("plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next.get_knowledge_conn", return_value=Connection()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next.feishu_service.resolve_wiki_node") as resolve:
        result = save_catalog_config({"url": "https://li.feishu.cn/wiki/SEqFwOafKi0zeJkOckvciGXbngh"},
                                     CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert result["configured"] is True
    assert statements[0][1][2:4] == ("SEqFwOafKi0zeJkOckvciGXbngh", "总表")
    resolve.assert_not_called()


def test_wiki_sheet_read_failure_never_opens_catalog_write_transaction():
    from backend.capabilities.models_next import CapabilityContext
    from plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next import sync_catalog
    from unittest.mock import patch

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, _params): assert sql.startswith("SELECT source_url,app_token,table_id")
        def fetchone(self): return {"source_url": "https://li.feishu.cn/wiki/SEqFwOafKi0zeJkOckvciGXbngh",
                                    "app_token": "SEqFwOafKi0zeJkOckvciGXbngh", "table_id": "总表"}
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    with patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={
        "gid": "admin", "team_id": "team_1", "system_role": "super_admin", "is_active": True,
    }), patch("plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next.get_knowledge_conn", return_value=Connection()) as connect, \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next.feishu_service.resolve_wiki_node", return_value={"obj_type": "sheet", "obj_token": "VlNasZDMphGVwYtrgZOcKaTBnsg"}), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next.feishu_service.list_spreadsheet_sheets", side_effect=RuntimeError("Feishu permission denied")):
        with pytest.raises(RuntimeError, match="permission denied"):
            sync_catalog({}, CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert connect.call_count == 1


def test_sheet_service_uses_bounded_read_only_ranges():
    from backend.services.feishu_service import FeishuService
    from unittest.mock import Mock, patch

    service = FeishuService()
    response = Mock()
    response.json.return_value = {"code": 0, "data": {"valueRange": {"values": [["名称", "飞书文档"]]}}}
    with patch.object(service, "_get_tenant_token", return_value="test-token"), \
         patch("backend.services.feishu_service.requests.get", return_value=response) as get:
        assert service.read_spreadsheet_values("VlNasZDMphGVwYtrgZOcKaTBnsg", "sxj5ws", 1, 100) == [["名称", "飞书文档"]]
    assert "/values/sxj5ws!A1:AZ100" in get.call_args.args[0]
    with pytest.raises(ValueError, match="out of bounds"):
        service.read_spreadsheet_values("VlNasZDMphGVwYtrgZOcKaTBnsg", "sxj5ws", 1, 1000)
