from plugins.agent.agent_backend.ai_assistant import tool_executor
from plugins.agent.agent_backend.data.confirmation_repository import (
    InMemoryConfirmationRepository,
    SqlConfirmationRepository,
)
from threading import Lock
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta


def setup_function() -> None:
    tool_executor.configure_confirmation_store(InMemoryConfirmationRepository())


def test_confirmation_token_is_bound_and_bad_attempt_does_not_consume_it() -> None:
    token = tool_executor.issue_confirm_token("cap__project__task__change__apply__v1", {"name": "x"}, "session-1", "user-1")

    assert tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-2", "user-1") == (False, {})
    assert tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-1", "user-2") == (False, {})

    valid, pending = tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-1", "user-1")
    assert valid is True
    assert pending["inputs"] == {"name": "x"}
    assert tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-1", "user-1") == (False, {})


def test_gateway_failure_releases_reserved_token_and_concurrent_replay_is_blocked() -> None:
    name = "cap__project__task__change__apply__v1"
    token = tool_executor.issue_confirm_token(
        name, {"name": "x"}, "session-1", "user-1",
        catalog_release="rel-1", capability_id="project.task.change.apply", major_version=1,
    )
    args = dict(
        catalog_release="rel-1", capability_id="project.task.change.apply", major_version=1,
    )

    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args)[0] is True
    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args) == (False, {})
    tool_executor.finish_confirm_token(token, accepted=False)
    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args)[0] is True
    tool_executor.finish_confirm_token(token, accepted=True)
    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args) == (False, {})


def test_confirmation_token_survives_worker_store_reconstruction() -> None:
    records = {}
    lock = Lock()
    tool_executor.configure_confirmation_store(InMemoryConfirmationRepository(records, lock))
    name = "cap__project__task__change__apply__v1"
    token = tool_executor.issue_confirm_token(
        name, {"name": "x"}, "session-1", "user-1",
        catalog_release="rel-1", capability_id="project.task.change.apply",
        idempotency_key="stable-idem-1",
    )

    tool_executor.configure_confirmation_store(InMemoryConfirmationRepository(records, lock))
    valid, pending = tool_executor.begin_confirm_token(
        token, name, "session-1", "user-1",
        catalog_release="rel-1", capability_id="project.task.change.apply",
    )

    assert valid is True
    assert pending["idempotency_key"] == "stable-idem-1"


def test_sql_confirmation_token_survives_repository_restart_and_uses_cas() -> None:
    rows = {}

    class Cursor:
        rowcount = 0
        row = None
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params=()):
            self.rowcount = 0
            if sql.startswith("INSERT"):
                keys = (
                    "token_hash", "tool_name", "inputs_json", "session_gid", "user_gid",
                    "catalog_release", "capability_id", "major_version", "payload_hash",
                    "idempotency_key", "agent_identity_json", "expires_at",
                )
                row = dict(zip(keys, params)); row["state"] = "pending"
                rows[row["token_hash"]] = row; self.rowcount = 1
            elif sql.startswith("UPDATE") and "SET state='inflight'" in sql:
                token_hash, tool_name, session_gid, user_gid, major_version, *optional = params
                row = rows.get(token_hash)
                matches = bool(
                    row and row["state"] == "pending"
                    and row["expires_at"] > datetime.now(UTC).replace(tzinfo=None)
                    and row["tool_name"] == tool_name and row["session_gid"] == session_gid
                    and row["user_gid"] == user_gid and row["major_version"] == major_version
                )
                if "catalog_release=%s" in sql:
                    matches = matches and row["catalog_release"] == optional.pop(0)
                if "capability_id=%s" in sql:
                    matches = matches and row["capability_id"] == optional.pop(0)
                if matches: row["state"] = "inflight"; self.rowcount = 1
            elif sql.startswith("SELECT"):
                self.row = dict(rows[params[0]]) if params[0] in rows else None
            elif sql.startswith("UPDATE") and "SET state='pending'" in sql:
                row = rows.get(params[0])
                if row and row["state"] == "inflight": row["state"] = "pending"; self.rowcount = 1
            elif sql.startswith("DELETE"):
                if "expires_at<=UTC_TIMESTAMP" in sql:
                    expired = [
                        key for key, row in rows.items()
                        if row["expires_at"] <= datetime.now(UTC).replace(tzinfo=None)
                    ][:params[0]]
                    for key in expired: rows.pop(key)
                    self.rowcount = len(expired)
                else:
                    row = rows.get(params[0])
                    if row and row["state"] == "inflight": rows.pop(params[0]); self.rowcount = 1
        def fetchone(self): return self.row

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()

    @contextmanager
    def connect():
        yield Connection()

    token_hash = "a" * 64
    record = {
        "tool_name": "cap__project__task__change__apply__v1", "inputs": {"name": "x"},
        "session_gid": "session-1", "user_gid": "user-1", "catalog_release": "rel-1",
        "capability_id": "project.task.change.apply", "major_version": 1,
        "payload_hash": tool_executor._payload_hash({"name": "x"}),
        "idempotency_key": "stable-idem-1", "agent_identity": {},
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }
    expected = {
        "tool_name": record["tool_name"], "session_gid": "session-1", "user_gid": "user-1",
        "catalog_release": "rel-1", "capability_id": "project.task.change.apply", "major_version": 1,
    }
    worker_one = SqlConfirmationRepository(connect)
    rows["expired"] = {
        **record, "token_hash": "expired", "state": "pending",
        "expires_at": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
    }
    worker_one.save(token_hash, record)
    assert "expired" not in rows
    worker_two_after_restart = SqlConfirmationRepository(connect)

    assert worker_two_after_restart.begin(token_hash, expected)["idempotency_key"] == "stable-idem-1"
    assert worker_one.begin(token_hash, expected) is None
    worker_two_after_restart.finish(token_hash, accepted=False)
    assert worker_one.begin(token_hash, expected) is not None
    worker_one.finish(token_hash, accepted=True)
    assert worker_two_after_restart.begin(token_hash, expected) is None
