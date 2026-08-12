from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from backend.capability_v2.outcomes import OutcomeRecord, SqlOutcomeStore
from backend.capability_v2.reliability import ApprovalService, SqlApprovalStore
from backend.tests.test_capability_reliability_pipeline import (
    _descriptor, _envelope, _result,
)


class Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.statements.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return self.rows.pop(0) if self.rows else []


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def connections(cursor, entries):
    @contextmanager
    def factory():
        entries.append(True)
        yield Connection(cursor)
    return factory


def test_sql_approval_store_persists_only_token_hash():
    cursor = Cursor()
    entries = []
    service = ApprovalService(SqlApprovalStore(connections(cursor, entries)))
    issued = service.issue(
        _descriptor(), _envelope(), resource_refs=("project:p1",),
        policy_version="policy-7",
    )

    sql, params = cursor.statements[0]
    assert "token_hash" in sql
    assert issued.token not in params
    assert issued.challenge.token_hash in params
    assert len(entries) == 1


def test_sql_outcome_completion_updates_outcome_and_enqueues_audit_in_one_transaction():
    envelope = _envelope()
    started = OutcomeRecord(
        operation_id="op_1", request_id=envelope.request_id,
        idempotency_scope="idem:scope", payload_hash="sha256:" + "a" * 64,
        capability_id=envelope.capability_id, major_version=1,
        tenant_id="tenant_1", consumer_scope="consumer:scope",
        actor_id="user_1", consumer_type="agent", consumer_id="agent.runtime",
        consumer_instance_id="run_a",
        policy_version="policy-7", status="started", started_at=datetime.now(UTC),
    )
    row = started.model_dump(mode="python")
    row["started_at"] = datetime.now()  # MySQL DATETIME values are returned without tzinfo.
    cursor = Cursor([row])
    entries = []
    domain_result = _result(envelope).model_copy(update={"data": {"domain_secret": "must-not-persist"}})
    completed = SqlOutcomeStore(connections(cursor, entries)).complete("op_1", domain_result)

    statements = [sql for sql, _params in cursor.statements]
    assert statements[0].startswith("SELECT") and "FOR UPDATE" in statements[0]
    assert statements[1].startswith("UPDATE")
    assert statements[2].startswith("INSERT") and "audit_outbox" in statements[2]
    assert completed.status == "completed"
    assert completed.started_at.tzinfo is not None
    update_params = cursor.statements[1][1]
    assert "must-not-persist" not in update_params[1]
    assert completed.result.data is None
    assert len(entries) == 1


def test_reliability_migration_has_hash_only_approval_and_atomic_outcome_tables():
    root = Path(__file__).resolve().parents[2]
    sql = (root / "backend/db/migrations/202608100003_base_capability_outcomes_and_approvals.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "token_hash" in sql
    assert "raw_token" not in sql and "plain_token" not in sql
    assert "workmanship_base_capability_outcomes" in sql
    assert "workmanship_base_capability_audit_outbox" in sql
    assert "workmanship_base_capability_audit_ledger" in sql
    assert "unique key uq_base_capability_outcome_idempotency" in sql

    worker = (
        root / "plugins/knowledge/knowledge_backend/infrastructure/publication_outbox_worker.py"
    ).read_text(encoding="utf-8")
    assert "deliver_capability_audit_once" in worker
    assert "INSERT IGNORE INTO workmanship_base_capability_audit_ledger" in worker
