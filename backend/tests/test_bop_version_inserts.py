import sys
import asyncio
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.craft.craft_backend.routers._bop import versions, fork, templates


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


def test_create_version_delegates_to_governed_capability(monkeypatch):
    captured = {}

    async def invoke(*args, **kwargs):
        captured["payload"] = args[5]
        captured["write"] = kwargs["write"]
        return {"version_gid": "created-version", "status": "active", "revision": 1, "entries_count": 0}

    monkeypatch.setattr(versions, '_invoke_factory', invoke)
    body = versions.CreateBopVersionBody(version_tag='V001', bop_name='空白版本')
    result = asyncio.run(versions.create_version(body, SimpleNamespace(headers={}), DummyUser(gid='user-1'), object(), object()))

    assert captured["payload"]["source"] == "empty"
    assert captured["payload"]["version_tag"] == "V001"
    assert captured["write"] is True
    assert result["data"]["gid"] == "created-version"


def test_update_version_uses_revision_pinned_preview_and_apply(monkeypatch):
    calls = []

    async def invoke(*args, **kwargs):
        capability = args[4]
        payload = args[5]
        calls.append((capability, payload, kwargs.get("write", False)))
        if capability == "craft.bop.version.get":
            if len([item for item in calls if item[0] == capability]) == 1:
                return {"version_gid": "v1", "revision": 3}
            return {"version_gid": "v1", "revision": 4, "version_tag": "V2"}
        if capability == "craft.bop.draft.change.preview":
            return {"preview_gid": "preview-1"}
        return {"version_gid": "v1", "revision": 4}

    monkeypatch.setattr(versions, '_invoke_factory', invoke)
    body = versions.UpdateBopVersionBody(version_tag="V2")
    result = asyncio.run(versions.update_version("v1", body, SimpleNamespace(headers={}), DummyUser(gid='user-1'), object(), object()))

    assert calls[0][0] == "craft.bop.version.get"
    assert calls[1][0] == "craft.bop.draft.change.preview"
    assert calls[1][1]["expected_revision"] == 3
    assert calls[1][1]["commands"][0]["changes"] == {"version_tag": "V2"}
    assert calls[2] == ("craft.bop.draft.change.apply", {"preview_gid": "preview-1"}, True)
    assert result["data"]["version_tag"] == "V2"


def test_fork_version_insert_includes_required_defaults(monkeypatch):
    cursor = FakeCursor(
        fetchone_results=[
            {'gid': 'src', 'project_gid': 'p1', 'factory_gid': 'f1', 'vehicle_model_gid': 'vm1', 'maturity': 'concept', 'takt_time': 60, 'bop_name': '源版本'},
            {'gid': 'forked'},
        ],
        fetchall_results=[[]],
    )
    conn = FakeConn(cursor)

    monkeypatch.setattr(fork, 'get_conn', FakeGetConn(conn))
    monkeypatch.setattr(fork, 'next_gid', lambda: 'forked-gid')

    body = fork.ForkBody(target_version_tag='V002')
    result = fork.fork_version('src', body, DummyUser(gid='user-1'))

    insert_sql, insert_params = next((sql, params) for sql, params in cursor.executed if 'INSERT INTO workmanship_bop_bop_versions' in sql)
    assert 'status' in insert_sql
    assert 'meta' in insert_sql
    assert 'lifecycle_phase' in insert_sql
    assert 'lifecycle_state' in insert_sql
    assert result == {'data': {'gid': 'forked'}, 'entries_count': 0}


def test_fork_entry_insert_includes_required_defaults(monkeypatch):
    cursor = FakeCursor(
        fetchone_results=[
            {'gid': 'src', 'project_gid': 'p1', 'factory_gid': 'f1', 'vehicle_model_gid': 'vm1', 'maturity': 'concept', 'takt_time': 60, 'bop_name': '源版本'},
            {'gid': 'forked'},
        ],
        fetchall_results=[[
            {
                'gid': 'entry-1', 'parent_gid': None, 'node_type': 'process', 'sort_order': 1,
                'level': 0, 'ai00_level': 4, 'title': '工序A', 'vpps': None, 'vpps_desc': None,
                'parent_bop_title': None, 'child_vpps': [], 'owner_gid': None, 'meta': {}
            }
        ]],
    )
    conn = FakeConn(cursor)

    monkeypatch.setattr(fork, 'get_conn', FakeGetConn(conn))
    monkeypatch.setattr(fork, 'next_gid', lambda: 'forked-gid')

    body = fork.ForkBody(target_version_tag='V002')
    fork.fork_version('src', body, DummyUser(gid='user-1'))

    entry_insert_sql, entry_insert_params = next((sql, params) for sql, params in cursor.executed if 'INSERT INTO workmanship_bop_bop_entries' in sql)
    assert 'vpps_part' in entry_insert_sql
    assert 'part_feed' in entry_insert_sql
    assert entry_insert_params[10] == ''
    assert entry_insert_params[11] is False


def test_template_entry_insert_includes_required_defaults(monkeypatch):
    cursor = FakeCursor(
        fetchone_results=[
            {'gid': 'src', 'project_gid': 'p1', 'factory_gid': 'f1', 'vehicle_model_gid': 'vm1', 'maturity': 'concept', 'takt_time': 60},
            {'gid': 'template'},
        ],
        fetchall_results=[[
            {
                'gid': 'entry-1', 'parent_gid': None, 'node_type': 'station_process', 'sort_order': 1,
                'level': 0, 'ai00_level': 2, 'title': '工位A', 'vpps': None, 'vpps_desc': None,
                'parent_bop_title': None, 'child_vpps': [], 'owner_gid': None, 'meta': {}
            }
        ]],
    )
    conn = FakeConn(cursor)

    monkeypatch.setattr(templates, 'get_conn', FakeGetConn(conn))
    monkeypatch.setattr(templates, 'next_gid', lambda: 'template-gid')

    body = templates.SaveAsTemplateBody(factory_gid='f1', template_name='模板A')
    templates.save_as_template('src', body, DummyUser(gid='user-1'))

    entry_insert_sql, entry_insert_params = next((sql, params) for sql, params in cursor.executed if 'INSERT INTO workmanship_bop_bop_entries' in sql)
    assert 'vpps_part' in entry_insert_sql
    assert 'part_feed' in entry_insert_sql
    assert entry_insert_params[10] == ''
    assert entry_insert_params[11] is False


