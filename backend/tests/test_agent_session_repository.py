import unittest
from contextlib import contextmanager

from plugins.agent.agent_backend.data.session_repository import SessionRepository


class FakeCursor:
    def __init__(self, responses):
        self.responses = responses
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.responses.pop(0) if self.responses else None

    def fetchall(self):
        return self.responses.pop(0) if self.responses else []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def factory(cursor):
    @contextmanager
    def connect():
        yield FakeConnection(cursor)

    return connect


class AgentSessionRepositoryTests(unittest.TestCase):
    def test_private_session_requires_owner(self):
        repo = SessionRepository(factory(FakeCursor([])), lambda: "session-1")
        with self.assertRaises(ValueError):
            repo.create_session("")
        with self.assertRaises(ValueError):
            repo.list_sessions("")

    def test_list_always_filters_by_user(self):
        cursor = FakeCursor([[]])
        repo = SessionRepository(factory(cursor))
        repo.list_sessions("user-7")
        sql, params = cursor.executed[0]
        self.assertIn("WHERE user_gid=%s", sql)
        self.assertEqual(params, ("user-7",))

    def test_repository_contains_no_runtime_ddl(self):
        cursor = FakeCursor([])
        repo = SessionRepository(factory(cursor), lambda: "session-1")
        repo.create_session("user-7")
        self.assertFalse(any("CREATE TABLE" in sql.upper() or "ALTER TABLE" in sql.upper() for sql, _ in cursor.executed))

    def test_mysql_turn_insert_has_no_postgres_cast(self):
        cursor = FakeCursor([{"max_sort_order": 2}])
        repo = SessionRepository(factory(cursor), lambda: "turn-1")
        repo.add_turn("session-1", "user", "hello", [])
        insert_sql = cursor.executed[1][0]
        self.assertNotIn("::jsonb", insert_sql)
        self.assertIn("workmanship_app_ai_turns", insert_sql)


if __name__ == "__main__":
    unittest.main()
