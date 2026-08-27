from __future__ import annotations

from contextlib import contextmanager
from threading import Lock, Thread


class _RoleDatabase:
    def __init__(self):
        self.rows = {
            "admin_a": {"gid": "admin_a", "system_role": "team_admin", "is_active": True},
            "admin_b": {"gid": "admin_b", "system_role": "team_admin", "is_active": True},
            "super_a": {"gid": "super_a", "system_role": "super_admin", "is_active": True},
            "super_b": {"gid": "super_b", "system_role": "super_admin", "is_active": True},
        }
        self.lock = Lock()
        self.connections: list[_Connection] = []

    @contextmanager
    def connection(self):
        conn = _Connection(self)
        self.connections.append(conn)
        try:
            yield conn
        finally:
            if conn.locked:
                self.lock.release()


class _Connection:
    def __init__(self, database: _RoleDatabase):
        self.database = database
        self.locked = False
        self.statements: list[str] = []

    @contextmanager
    def cursor(self):
        yield _Cursor(self)

    def commit(self):
        return None


class _Cursor:
    def __init__(self, connection: _Connection):
        self.connection = connection
        self.rows: list[dict] = []

    def execute(self, sql, params=()):
        self.connection.statements.append(sql)
        database = self.connection.database
        if "FOR UPDATE" in sql and not self.connection.locked:
            database.lock.acquire()
            self.connection.locked = True
        if "WHERE gid IN" in sql:
            self.rows = [dict(database.rows[gid]) for gid in sorted(set(params)) if gid in database.rows]
        elif "WHERE system_role='super_admin'" in sql:
            self.rows = [dict(row) for row in database.rows.values()
                         if row["system_role"] == "super_admin" and row["is_active"]]
        elif sql.startswith("UPDATE workmanship_auth_users"):
            role, _subtype, _org_role, target_gid = params
            database.rows[target_gid]["system_role"] = role
            self.rows = []
        elif "WHERE gid=%s" in sql:
            self.rows = [dict(database.rows[params[0]])] if params[0] in database.rows else []
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


def test_concurrent_super_admin_demotions_use_one_locked_transaction(monkeypatch):
    from backend.base import structural_web

    database = _RoleDatabase()
    monkeypatch.setattr(structural_web, "get_conn", database.connection)
    failures: list[Exception] = []

    def demote(operator_gid: str, target_gid: str) -> None:
        try:
            structural_web.assign_user_role(
                actor={"gid": operator_gid, "system_role": "team_admin"},
                user_gid=target_gid, new_role="member", external_subtype=None,
            )
        except structural_web.StructuralWebError as exc:
            failures.append(exc)

    first = Thread(target=demote, args=("admin_a", "super_a"))
    second = Thread(target=demote, args=("admin_b", "super_b"))
    first.start()
    second.start()
    first.join()
    second.join()

    assert sum(row["system_role"] == "super_admin" for row in database.rows.values()) == 1
    assert len(failures) == 1
    assert "至少保留" in str(failures[0])
    assert len(database.connections) == 2
    update_count = 0
    for connection in database.connections:
        assert sum("FOR UPDATE" in sql for sql in connection.statements) >= 2
        update_count += sum(sql.startswith("UPDATE workmanship_auth_users") for sql in connection.statements)
    assert update_count == 1
