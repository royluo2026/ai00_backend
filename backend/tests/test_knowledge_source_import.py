"""Only an explicit, current, complete source candidate may advance Markdown and its baseline."""
from unittest.mock import patch
import hashlib

import pytest

from backend.capabilities.models_next import CapabilityContext, CapabilityBusinessError
from plugins.knowledge.knowledge_backend.capabilities.feishu_import_next import confirm_import


class Cursor:
    def __init__(self, *, complete=True, current="rev_2"):
        self.complete = complete
        self.current = current
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()): self.sql = sql; self.calls.append((sql, params))
    def fetchone(self):
        if "workmanship_know_feishu_imports" in self.sql: return None
        if "workmanship_know_feishu_snapshots" in self.sql:
            return {"snapshot_gid": "snap_1", "source_gid": "source_1", "document_url": "https://example.feishu.cn/docx/doc123",
                    "linked_document_gid": "doc_1", "complete": self.complete, "object_key": "source-key", "content_sha256": "a" * 64,
                    "title": "BOP"}
        if "workmanship_know_documents" in self.sql:
            return {"gid": "doc_1", "created_by": "creator", "space_gid": "space_1", "title": "BOP",
                    "current_revision_gid": self.current, "before_sha256": "b" * 64}
        return None


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value
    def commit(self): pass
    def rollback(self): pass


def _context(): return CapabilityContext(user_gid="admin", team_gid="team_1")
def _profile(): return {"gid": "admin", "team_id": "team_1", "system_role": "super_admin", "is_active": True}
def _payload(): return {"source_snapshot_gid": "snap_1", "expected_revision_gid": "rev_1", "markdown": "# BOP\n", "idempotency_key": "request-1"}


def test_stale_ois_revision_rejects_confirm_before_any_write():
    cursor = Cursor(current="rev_2")
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()):
        with pytest.raises(CapabilityBusinessError, match="changed"):
            confirm_import(_payload(), _context())
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.calls)


def test_incomplete_candidate_cannot_be_confirmed():
    cursor = Cursor(complete=False)
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()):
        with pytest.raises(ValueError, match="incomplete"):
            confirm_import(_payload(), _context())
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.calls)


class SuccessCursor(Cursor):
    def __init__(self, *, source_unchanged=False, complete=True, diagnostics=None):
        super().__init__(current="rev_1")
        self.source_unchanged = source_unchanged
        self.complete = complete
        self.diagnostics = diagnostics or []
    def fetchone(self):
        if "workmanship_know_feishu_baselines" in self.sql:
            return {"snapshot_gid": "old", "content_sha256": "a" * 64 if self.source_unchanged else "c" * 64}
        if "MAX(revision_no)" in self.sql: return {"n": 1}
        if "SELECT revision_no FROM" in self.sql: return {"revision_no": 1}
        row = super().fetchone()
        if "workmanship_know_feishu_snapshots" in self.sql and row:
            return {**row, "complete": self.complete, "diagnostics_json": self.diagnostics}
        return row


def test_reviewed_visual_references_can_be_confirmed_but_unknown_content_cannot():
    visual = [{"block_id": "image_1", "code": "image_requires_manual_review"}]
    cursor = SuccessCursor(complete=False, diagnostics=visual)
    conn = TrackedConnection(cursor)
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=conn), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_immutable", return_value=b"# Feishu image reference\n"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.new_knowledge_id", side_effect=lambda kind: f"{kind}_new"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.store_markdown_revision", side_effect=lambda prepared: {
             "object_key": prepared.object_key, "sha256": prepared.sha256, "byte_size": len(prepared.data), "media_type": prepared.media_type,
         }):
        result = confirm_import({**_payload(), "visuals_reviewed": True}, _context())
    assert result.data["changed"] is True
    cursor = SuccessCursor(complete=False, diagnostics=visual + [{"block_id": "unknown", "code": "unsupported_block"}])
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()):
        with pytest.raises(ValueError, match="incomplete"):
            confirm_import({**_payload(), "visuals_reviewed": True}, _context())


class TrackedConnection(Connection):
    def __init__(self, cursor): super().__init__(cursor); self.commits = 0; self.rollbacks = 0
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def test_confirm_advances_baseline_only_after_ois_revision_is_stored():
    cursor = SuccessCursor(); conn = TrackedConnection(cursor)
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=conn), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_immutable", return_value=b"# from Feishu\n"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.new_knowledge_id", side_effect=lambda kind: f"{kind}_new"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.store_markdown_revision", side_effect=lambda prepared: {
             "object_key": prepared.object_key, "sha256": prepared.sha256, "byte_size": len(prepared.data), "media_type": prepared.media_type,
         }):
        result = confirm_import(_payload(), _context())
    assert result.data["changed"] is True
    assert conn.commits == 1 and conn.rollbacks == 0
    sqls = [sql for sql, _ in cursor.calls]
    assert next(i for i, sql in enumerate(sqls) if "INSERT INTO workmanship_know_revisions" in sql) < next(i for i, sql in enumerate(sqls) if "INSERT INTO workmanship_know_feishu_baselines" in sql)


def test_ois_failure_does_not_advance_baseline():
    cursor = SuccessCursor(); conn = TrackedConnection(cursor)
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=conn), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_immutable", return_value=b"# from Feishu\n"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.new_knowledge_id", side_effect=lambda kind: f"{kind}_new"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.store_markdown_revision", side_effect=RuntimeError("OIS failed")):
        with pytest.raises(RuntimeError, match="OIS failed"):
            confirm_import(_payload(), _context())
    assert conn.commits == 0 and conn.rollbacks == 1
    assert not any("INSERT INTO workmanship_know_feishu_baselines" in sql for sql, _ in cursor.calls)


def test_same_source_and_same_markdown_is_a_noop():
    cursor = SuccessCursor(source_unchanged=True)
    cursor_sha = hashlib.sha256(b"# BOP\n").hexdigest()
    original = cursor.fetchone
    def fetchone():
        row = original()
        if "workmanship_know_documents" in cursor.sql and row:
            return {**row, "before_sha256": cursor_sha}
        return row
    cursor.fetchone = fetchone
    conn = TrackedConnection(cursor)
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=conn), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_immutable", return_value=b"# BOP\n"):
        result = confirm_import(_payload(), _context())
    assert result.data["changed"] is False
    assert not any("INSERT INTO workmanship_know_revisions" in sql for sql, _ in cursor.calls)


def test_retried_idempotency_key_returns_original_receipt_without_write():
    cursor = Cursor()
    def prior():
        if "workmanship_know_feishu_imports" in cursor.sql:
            return {"source_gid": "source_1", "snapshot_gid": "snap_1", "request_sha256": "same",
                    "document_gid": "doc_1", "revision_gid": "rev_2", "revision_no": 2, "changed": True}
        raise AssertionError("retry must not read or write more state")
    cursor.fetchone = prior
    with patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile()), \
         patch("plugins.knowledge.knowledge_backend.capabilities.feishu_import_next._request_hash", return_value="same"):
        result = confirm_import(_payload(), _context())
    assert result.data["revision_gid"] == "rev_2"
    assert len(cursor.calls) == 1
