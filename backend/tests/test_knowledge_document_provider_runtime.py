"""The official Knowledge Provider enforces the same edit contract as its compatibility path."""
from unittest.mock import patch

import pytest

from backend.capabilities.models_next import CapabilityContext
from backend.tests.test_knowledge_document_edit_access import _Connection, _Cursor, _profile
from plugins.knowledge.knowledge_backend.capabilities.knowledge_documents_next import revise_document


@pytest.mark.parametrize("collaborator,role,allowed", [
    (False, "member", False),
    (True, "member", True),
    (False, "super_admin", True),
])
def test_official_provider_revise_requires_document_editor(collaborator, role, allowed):
    cursor = _Cursor(collaborator=collaborator)
    with patch("plugins.knowledge.knowledge_backend.data.connection.get_knowledge_conn", return_value=_Connection(cursor)), \
         patch("backend.platform_sdk.identity.get_active_identity_profile", return_value=_profile(role)), \
         patch("plugins.knowledge.knowledge_backend.capabilities.knowledge_documents_next.new_knowledge_id", return_value="rev_2"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.knowledge_documents_next.prepare_markdown_revision", return_value="prepared"), \
         patch("plugins.knowledge.knowledge_backend.capabilities.knowledge_documents_next.store_markdown_revision", return_value={
             "object_key": "knowledge/rev_2.md", "sha256": "b" * 64,
             "byte_size": 4, "media_type": "text/markdown; charset=utf-8",
         }):
        action = lambda: revise_document({"document_gid": "doc_1", "base_revision_gid": "rev_1", "markdown": "new\n"}, CapabilityContext(user_gid="reader", team_gid="team_1"))
        if allowed:
            assert action().data["revision_gid"] == "rev_2"
        else:
            with pytest.raises(PermissionError): action()
    if not allowed:
        assert not any("INSERT INTO workmanship_know_revisions" in sql for sql, _ in cursor.calls)
