"""A Feishu pull creates a source candidate, never an accepted OIS revision."""
from unittest.mock import patch
import hashlib

import pytest

from backend.capabilities.models_next import CapabilityContext
from plugins.knowledge.knowledge_backend.capabilities.feishu_source_next import pull_source, batch_pull_sources, get_latest_source_snapshot
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityOutput


class Cursor:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()): self.sql = sql; self.calls.append((sql, params))
    def fetchone(self):
        if "workmanship_know_feishu_sources" in self.sql:
            return {"gid": "knf_1", "tenant_gid": "team_1", "document_url": "https://example.feishu.cn/docx/doc123", "document_token": "doc123", "linked_document_gid": None}
        return None


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value
    def commit(self): pass


def _profile(): return {"gid": "admin", "team_id": "team_1", "system_role": "super_admin", "is_active": True}


def test_pull_stores_candidate_without_creating_document_revision():
    cursor = Cursor()
    blocks = [{"block_id": "root", "block_type": 1, "children": ["p"]},
              {"block_id": "p", "block_type": 2, "text": {"elements": [{"text_run": {"content": "BOP"}}]}}]
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.user_credential", return_value="user-token"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.read_document_blocks", return_value=("doc123", blocks)) as read_blocks, \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.put_immutable", side_effect=lambda key, data, _type: {"object_key": key, "sha256": hashlib.sha256(data).hexdigest()}), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.new_knowledge_id", return_value="snapshot_1"):
        result = pull_source({"source_gid": "knf_1"}, CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert result.data["complete"] is True
    read_blocks.assert_called_once_with("https://example.feishu.cn/docx/doc123", access_token="user-token")
    assert "BOP" in result.data["markdown"]
    assert any("INSERT INTO workmanship_know_feishu_snapshots" in sql for sql, _ in cursor.calls)
    assert not any("workmanship_know_revisions" in sql for sql, _ in cursor.calls)


def test_partial_feishu_read_does_not_write_snapshot():
    cursor = Cursor()
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.user_credential", return_value="user-token"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.read_document_blocks", side_effect=ValueError("incomplete page")):
        with pytest.raises(ValueError, match="incomplete"):
            pull_source({"source_gid": "knf_1"}, CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert not any(sql.startswith("INSERT") for sql, _ in cursor.calls)


def test_feishu_application_error_reports_delegated_permission_failure():
    cursor = Cursor()
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.user_credential", return_value="user-token"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.read_document_blocks",
               side_effect=ValueError("Feishu Wiki lookup failed: 131006")):
        with pytest.raises(CapabilityBusinessError) as caught:
            pull_source({"source_gid": "knf_1"}, CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert caught.value.code == "feishu_document_view_denied"
    assert not any(sql.startswith("INSERT") for sql, _ in cursor.calls)


def test_batch_pull_isolates_failed_sources_and_does_not_publish_markdown():
    class BatchCursor(Cursor):
        def fetchall(self):
            return [{"source_gid": "knf_1", "title": "BOP"}, {"source_gid": "knf_2", "title": "设备"}]
    cursor = BatchCursor()
    successful = CapabilityOutput(data={"snapshot_gid": "snap_1", "complete": True}, evidence=())
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.pull_source", side_effect=[
             successful, CapabilityBusinessError("feishu_document_view_denied", "没有查看权限"),
         ]) as pull:
        result = batch_pull_sources({}, CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert pull.call_count == 2
    assert result.data["items"] == [
        {"source_gid": "knf_1", "title": "BOP", "status": "pulled", "snapshot_gid": "snap_1", "error_code": None, "message": None},
        {"source_gid": "knf_2", "title": "设备", "status": "failed", "snapshot_gid": None, "error_code": "feishu_document_view_denied", "message": "没有查看权限"},
    ]
    assert not any("workmanship_know_revisions" in sql for sql, _ in cursor.calls)


def test_latest_snapshot_reopens_batch_candidate_without_publishing():
    class LatestCursor(Cursor):
        def fetchone(self):
            if "workmanship_know_feishu_sources" in self.sql:
                return {"gid": "knf_1", "linked_document_gid": None}
            if "workmanship_know_feishu_snapshots" in self.sql:
                return {"gid": "snap_1", "complete": True}
            return None
    cursor = LatestCursor()
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_source_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()):
        result = get_latest_source_snapshot({"source_gid": "knf_1"}, CapabilityContext(user_gid="admin", team_gid="team_1"))
    assert result == {"source_gid": "knf_1", "snapshot_gid": "snap_1", "complete": True}
    assert not any(sql.startswith("INSERT") or sql.startswith("UPDATE") for sql, _ in cursor.calls)
