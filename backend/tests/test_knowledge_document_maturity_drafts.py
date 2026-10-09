"""Maturity and working copies must not mutate immutable revision history."""
from unittest.mock import patch

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.knowledge_documents_next import change_document_maturity, get_document_draft, save_document_draft


class Cursor:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()):
        self.sql = sql
        self.calls.append((sql, params))
    def fetchone(self):
        if "workmanship_know_documents" in self.sql:
            return {"gid": "doc_1", "tenant_gid": "team_1", "created_by": "creator", "maturity": "V1", "current_revision_gid": "rev_1"}
        return None


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value
    def commit(self): pass


def test_maturity_change_records_event_without_new_revision():
    cursor = Cursor()
    with patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={"gid": "creator", "team_id": "team_1", "system_role": "member", "is_active": True}):
        result = change_document_maturity({"document_gid": "doc_1", "maturity": "V2"}, CapabilityContext(user_gid="creator", team_gid="team_1"))
    assert result.data["maturity"] == "V2"
    assert any("INSERT INTO workmanship_know_document_maturity_events" in sql for sql, _ in cursor.calls)
    assert not any("INSERT INTO workmanship_know_revisions" in sql for sql, _ in cursor.calls)


def test_private_draft_save_does_not_create_revision():
    cursor = Cursor()
    with patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={"gid": "creator", "team_id": "team_1", "system_role": "member", "is_active": True}):
        result = save_document_draft({"document_gid": "doc_1", "base_revision_gid": "rev_1", "markdown": "# work"}, CapabilityContext(user_gid="creator", team_gid="team_1"))
    assert result.data["base_revision_gid"] == "rev_1"
    assert any("INSERT INTO workmanship_know_document_drafts" in sql for sql, _ in cursor.calls)
    assert not any("INSERT INTO workmanship_know_revisions" in sql for sql, _ in cursor.calls)


def test_private_draft_get_is_scoped_to_its_author():
    cursor = Cursor()
    with patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={"gid": "creator", "team_id": "team_1", "system_role": "member", "is_active": True}):
        result = get_document_draft({"document_gid": "doc_1"}, CapabilityContext(user_gid="creator", team_gid="team_1"))
    assert result.data["exists"] is False
    assert any("WHERE document_gid=%s AND user_gid=%s AND tenant_gid=%s" in sql and params == ("doc_1", "creator", "team_1") for sql, params in cursor.calls)
