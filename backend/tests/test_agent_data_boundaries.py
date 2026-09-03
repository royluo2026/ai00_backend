import unittest
from contextlib import contextmanager
from pathlib import Path

from plugins.agent.agent_backend.data.audit_repository import AuditRepository
from plugins.agent.agent_backend.data.memory_repository import MemoryRepository
from plugins.agent.agent_backend.data import connection as agent_connection
from backend.capability_v2.provider_contracts import CapabilityOutput, EvidenceRef


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


def test_agent_transaction_reuses_domain_connection_and_persists_owned_outbox(monkeypatch):
    cursor = Cursor()

    class TransactionConnection(Connection):
        committed = False
        rolled_back = False
        closed = False

        def commit(self): self.committed = True
        def rollback(self): self.rolled_back = True
        def close(self): self.closed = True

    connection = TransactionConnection(cursor)

    class Pool:
        def connection(self): return connection

    monkeypatch.setattr(agent_connection, "_get_pool", lambda: Pool())
    transaction = agent_connection.begin_agent_transaction()
    with agent_connection.get_agent_conn() as owned:
        assert owned is connection
    transaction.record_outbox(
        "agent.run.change.apply",
        1,
        type("Context", (), {
            "outcome_operation_id": "outcome-op-1",
            "async_operation_id": "async-op-1",
            "request_id": "req-1",
        })(),
        CapabilityOutput(
            data={"resource_gid": "run-1"},
            evidence=(EvidenceRef(kind="agent.change", reference="agent://run/run-1"),),
        ),
    )
    transaction.commit(); transaction.close()

    assert "INSERT INTO workmanship_agent_capability_outbox" in cursor.executed[0][0]
    assert "outcome_operation_id" in cursor.executed[0][0]
    assert cursor.executed[0][1][1:3] == ("outcome-op-1", "async-op-1")
    assert "workmanship_base_" not in cursor.executed[0][0]
    assert connection.committed is True
    assert connection.closed is True


if __name__ == "__main__":
    unittest.main()
