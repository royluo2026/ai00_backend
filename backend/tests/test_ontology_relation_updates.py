import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.routers import ontology


class FakeCursor:
    def __init__(self, fetchone_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.executed = []
        self.rowcount = 0

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


def test_update_relation_allows_noop_update_when_relation_exists(monkeypatch):
    cursor = FakeCursor(fetchone_results=[{'gid': '195820092603240448'}])
    cursor.rowcount = 0
    conn = FakeConn(cursor)

    monkeypatch.setattr(ontology, 'get_conn', FakeGetConn(conn))

    result = ontology.update_relation('195820092603240448', {'show_in_detail': False}, {'gid': 'user-1'})

    assert result == {'ok': True}
    assert conn.commits == 1
    assert cursor.executed[0][0].startswith('SELECT 1 FROM workmanship_onto_relations')
    assert cursor.executed[1][0].startswith('UPDATE workmanship_onto_relations SET show_in_detail=%s WHERE gid=%s')


def test_update_relation_returns_404_when_relation_missing(monkeypatch):
    cursor = FakeCursor(fetchone_results=[None])
    conn = FakeConn(cursor)

    monkeypatch.setattr(ontology, 'get_conn', FakeGetConn(conn))

    with pytest.raises(HTTPException) as exc:
        ontology.update_relation('195820092603240448', {'show_in_detail': False}, {'gid': 'user-1'})

    assert exc.value.status_code == 404
    assert exc.value.detail == '关系不存在'
    assert conn.commits == 0
