from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.craft.craft_backend.application import project_scope
from plugins.knowledge.knowledge_backend import public


def context():
    return SimpleNamespace(user_gid='actor', team_gid='team', permissions=('craft.read', 'knowledge.read'), active_roles=())


def test_craft_entry_scope_uses_current_owner_record_and_manager(monkeypatch):
    @contextmanager
    def connection():
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params):
                assert 'e.is_deleted=FALSE' in sql and 'v.archived_at IS NULL' in sql
                assert params == ('entry',)
            def fetchone(self): return {'project_gid': 'project'}
        yield SimpleNamespace(cursor=Cursor)
    monkeypatch.setattr(project_scope, 'get_conn', connection)
    from backend.platform_sdk import project_access
    monkeypatch.setattr(project_access, 'can_edit_project_bop', lambda actor, project, line, roles: actor=='actor' and project=='project')
    assert project_scope.entry_project_gid('entry', context()) == 'project'
    monkeypatch.setattr(project_access, 'can_edit_project_bop', lambda *args: False)
    with pytest.raises(CapabilityBusinessError): project_scope.entry_project_gid('entry', context())


def test_knowledge_entry_uses_entry_owner_visibility_not_legacy_items(monkeypatch):
    from plugins.knowledge.knowledge_backend.capabilities import knowledge_next
    def read(payload, ctx):
        assert payload == {'gid': 'entry'} and ctx.user_gid == 'actor'
        return SimpleNamespace(data={'gid':'entry','source_project_gid':'project','share_scope':'project','creator_gid':'actor'})
    monkeypatch.setattr(knowledge_next, 'get_knowledge', read)
    assert public.readable_entry_scope('entry', context()) == {'gid':'entry','source_project_gid':'project','share_scope':'project','creator_gid':'actor'}
    monkeypatch.setattr(knowledge_next, 'get_knowledge', lambda *args: (_ for _ in ()).throw(LookupError('private title')))
    with pytest.raises(CapabilityBusinessError, match='unavailable'): public.readable_entry_scope('entry', context())


def test_scope_resolvers_reject_missing_identity_and_read_permission():
    empty = SimpleNamespace(user_gid='', team_gid='', permissions=(), active_roles=())
    for resolver in (project_scope.entry_project_gid, public.readable_entry_scope):
        with pytest.raises(CapabilityBusinessError): resolver('entry', empty)
