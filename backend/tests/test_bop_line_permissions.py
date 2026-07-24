import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.craft.craft_backend.routers._bop import entries
from plugins.craft.craft_backend.routers._bop import _helpers


class FakeCursor:
    def __init__(self, fetchone_results=None, fetchall_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.executed = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


class FakeGetConn:
    def __init__(self, conn):
        self.conn = conn

    def __call__(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyUser(dict):
    pass


def test_member_can_edit_any_line_without_scope_lookup():
    cursor = FakeCursor()

    _helpers._check_line_editable(
        cursor,
        'ver-1',
        'entry-1',
        DummyUser(gid='user-1', org_role='member'),
    )

    assert cursor.executed == []


def test_patch_entity_detail_checks_line_permission_with_version_and_entry(monkeypatch):
    cursor = FakeCursor(
        fetchone_results=[
            {'version_gid': 'ver-1', 'entry_gid': 'entry-1'},
            {'ok': 1},
        ],
        fetchall_results=[[{'column_name': 'title'}]],
    )
    conn = FakeConn(cursor)
    seen = {}

    monkeypatch.setattr(entries, 'get_conn', FakeGetConn(conn))

    def fake_check_line_editable(cur, version_gid, entry_gid, user, allow_copy=False):
        seen['version_gid'] = version_gid
        seen['entry_gid'] = entry_gid
        seen['allow_copy'] = allow_copy

    monkeypatch.setattr(entries, '_check_line_editable', fake_check_line_editable)

    body = entries.EntityPatchBody(link_type='bop_process', ref_gid='entity-1', fields={'title': '新标题'})
    result = entries.patch_entity_detail(body, DummyUser(gid='user-1'))

    assert result == {'ok': True}
    assert seen == {'version_gid': 'ver-1', 'entry_gid': 'entry-1', 'allow_copy': False}



def test_patch_entity_detail_rejects_uneditable_line(monkeypatch):
    cursor = FakeCursor(fetchone_results=[{'version_gid': 'ver-1', 'entry_gid': 'entry-1'}])
    conn = FakeConn(cursor)

    monkeypatch.setattr(entries, 'get_conn', FakeGetConn(conn))

    def fake_check_line_editable(cur, version_gid, entry_gid, user, allow_copy=False):
        raise HTTPException(403, '当前线体无编辑权限（只读）')

    monkeypatch.setattr(entries, '_check_line_editable', fake_check_line_editable)

    body = entries.EntityPatchBody(link_type='bop_process', ref_gid='entity-1', fields={'title': '新标题'})
    with pytest.raises(HTTPException) as exc:
        entries.patch_entity_detail(body, DummyUser(gid='user-1'))

    assert exc.value.status_code == 403



def test_copy_entries_from_does_not_invoke_line_edit_check(monkeypatch):
    called = {'count': 0}

    def fake_do_copy(version_gid, src_gid, set_gbop_source, cut_node_types=None):
        return {
            'data': [{'gid': 'copied-entry'}],
            'count': 1,
            'version_gid': version_gid,
            'src_gid': src_gid,
            'set_gbop_source': set_gbop_source,
        }

    def fake_check_line_editable(*args, **kwargs):
        called['count'] += 1
        raise AssertionError('_check_line_editable should not be called for copy-from')

    monkeypatch.setattr(entries, '_do_copy', fake_do_copy)
    monkeypatch.setattr(entries, '_check_line_editable', fake_check_line_editable)

    result = entries.copy_entries_from('ver-target', 'ver-src', DummyUser(gid='user-1'))

    assert result['count'] == 1
    assert result['version_gid'] == 'ver-target'
    assert result['src_gid'] == 'ver-src'
    assert result['set_gbop_source'] is False
    assert called['count'] == 0



def test_copy_entries_from_gbop_does_not_invoke_line_edit_check(monkeypatch):
    called = {'count': 0}

    def fake_do_copy(version_gid, src_gid, set_gbop_source, cut_node_types=None):
        return {
            'data': [{'gid': 'copied-entry'}],
            'count': 1,
            'version_gid': version_gid,
            'src_gid': src_gid,
            'set_gbop_source': set_gbop_source,
        }

    def fake_check_line_editable(*args, **kwargs):
        called['count'] += 1
        raise AssertionError('_check_line_editable should not be called for copy-from-gbop')

    monkeypatch.setattr(entries, '_do_copy', fake_do_copy)
    monkeypatch.setattr(entries, '_check_line_editable', fake_check_line_editable)

    result = entries.copy_entries_from_gbop('ver-target', 'ver-src', DummyUser(gid='user-1'))

    assert result['count'] == 1
    assert result['version_gid'] == 'ver-target'
    assert result['src_gid'] == 'ver-src'
    assert result['set_gbop_source'] is True
    assert called['count'] == 0
