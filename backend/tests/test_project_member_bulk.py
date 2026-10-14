from backend.platform_sdk import project_access
import pytest


class Cursor:
    def __init__(self): self.inserts = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, args):
        if sql.startswith('INSERT'): self.inserts.append(args)
    def fetchall(self): return [{'user_gid': 'existing'}]


class Connection:
    def __init__(self): self.cur = Cursor(); self.commits = 0; self.rollbacks = 0
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self.cur
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def test_batch_members_is_one_transaction_and_skips_existing(monkeypatch):
    conn = Connection()
    monkeypatch.setattr(project_access, 'get_conn', lambda: conn)
    monkeypatch.setattr(project_access, 'get_user_profiles', lambda gids: {gid: {'gid': gid} for gid in gids})
    project_access.add_project_members('p', ['existing', 'new', 'new'])
    assert len(conn.cur.inserts) == 1
    assert conn.cur.inserts[0][2] == 'new'
    assert conn.commits == 1


def test_batch_members_rejects_missing_users_before_writing(monkeypatch):
    conn = Connection()
    monkeypatch.setattr(project_access, 'get_conn', lambda: conn)
    monkeypatch.setattr(project_access, 'get_user_profiles', lambda gids: {})
    with pytest.raises(ValueError): project_access.add_project_members('p', ['missing'])
    assert not conn.cur.inserts
