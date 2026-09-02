import unittest
from contextlib import contextmanager
from pathlib import Path

from plugins.agent.agent_backend.data.audit_repository import AuditRepository
from plugins.agent.agent_backend.data.memory_repository import MemoryRepository


class Cursor:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
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


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def factory(cursor):
    @contextmanager
    def connect():
        yield Connection(cursor)

    return connect


class AgentDataBoundaryTests(unittest.TestCase):
    def test_memory_requires_user_and_uses_mysql_upsert(self):
        cursor = Cursor()
        repository = MemoryRepository(factory(cursor), lambda: "memory-1")
        with self.assertRaises(ValueError):
            repository.list_for_user("")
        repository.save("user-1", "key", "content", "preference", True)
        sql, params = cursor.executed[0]
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)
        self.assertNotIn("ON CONFLICT", sql)
        self.assertEqual(params[1], "user-1")

    def test_memory_search_filters_in_sql_by_user(self):
        cursor = Cursor([[]])
        MemoryRepository(factory(cursor)).search("user-2", "fixture")
        sql, params = cursor.executed[0]
        self.assertIn("user_gid=%s", sql)
        self.assertEqual(params[0], "user-2")

    def test_audit_event_requires_authenticated_user(self):
        repository = AuditRepository(factory(Cursor()), lambda: "audit-1")
        with self.assertRaises(ValueError):
            repository.record({"tool_name": "x"})

    def test_agent_routers_have_no_runtime_ddl_or_base_db_import(self):
        root = Path(__file__).resolve().parents[2]
        paths = [
            root / "plugins/agent/agent_backend/routers/skills_v2.py",
            root / "plugins/agent/agent_backend/routers/ai_audit.py",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("from backend.db", text)
        self.assertNotIn("CREATE TABLE", text.upper())
        repository = (root / "plugins/agent/agent_backend/infrastructure/repository.py").read_text(encoding="utf-8")
        self.assertIn("owner_gid=%s OR scope='team' OR (scope='global' AND status='active')", repository)


if __name__ == "__main__":
    unittest.main()
