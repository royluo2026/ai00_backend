"""A collaborator picker only exposes active members of the caller's team."""
from unittest.mock import patch
from types import SimpleNamespace

from backend.services.user_service import search_users
from plugins.knowledge.knowledge_backend.capabilities.knowledge_documents_next import search_document_collaborators, register_knowledge_document_capabilities


class Cursor:
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params):
        self.sql, self.params = sql, params
    def fetchall(self): return []


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value


def test_collaborator_search_is_limited_to_the_active_tenant():
    cursor = Cursor()
    with patch("backend.services.user_service.get_conn", return_value=Connection(cursor)):
        assert search_users("王", 10, team_gid="team_1") == []
    assert "team_id = %s" in cursor.sql
    assert cursor.params == ("team_1", "%王%", "%王%", 10)


def test_collaborator_capability_passes_trusted_tenant_to_directory():
    context = SimpleNamespace(team_gid="team_1", user_gid="user_1")
    with patch("backend.platform_sdk.identity.get_active_identity_profile", return_value={"is_active": True, "team_id": "team_1", "system_role": "super_admin"}), \
         patch("backend.services.user_service.search_users", return_value=[]) as search:
        assert search_document_collaborators({"query": "王", "limit": 10}, context).data == {"items": [], "total": 0}
    search.assert_called_once_with("王", 10, team_gid="team_1")


def test_collaborator_search_is_registered_in_official_knowledge_provider():
    class Registry:
        def __init__(self): self.entries = {}
        def register(self, spec, handler, descriptor): self.entries[spec.id] = (spec, handler, descriptor)
    registry = Registry()
    register_knowledge_document_capabilities(registry)
    spec, handler, descriptor = registry.entries["knowledge.document.collaborator.search"]
    assert handler is search_document_collaborators
    assert spec.owner == "knowledge"
    assert descriptor.id == "knowledge.document.collaborator.search"
