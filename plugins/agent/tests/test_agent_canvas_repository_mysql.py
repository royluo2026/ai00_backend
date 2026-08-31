"""MySQL transaction gate for durable Agent canvas execution.

Set AI00_AGENT_TEST_DB_URL to a dedicated database whose name contains ``test``.
The account must own DDL and DML in that database. Set
AI00_REQUIRE_AGENT_MYSQL_TESTS=1 in the controlled gate so a missing URL fails
instead of skipping.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.agent.agent_backend.application.canvas_runtime import (
    CanvasResumeRequest, CanvasStartRequest, RunPrincipal, RuntimeDispatch,
)
from plugins.agent.agent_backend.application.service import CanvasExecutionCoordinator
from plugins.agent.agent_backend.domain.canvas_tokens import derive_canvas_token
from plugins.agent.agent_backend.infrastructure.repository import AgentCapabilityRepository


ROOT = Path(__file__).resolve().parents[3]
PRINCIPAL = RunPrincipal("task3-mysql-actor", "task3-mysql-team")
TOKEN_SECRET = b"task-3-mysql-integration-secret"
SKILL_GID = "task3-mysql-skill"


def _database_params() -> dict:
    raw = os.getenv("AI00_AGENT_TEST_DB_URL", "")
    if not raw:
        if os.getenv("AI00_REQUIRE_AGENT_MYSQL_TESTS") == "1":
            pytest.fail(
                "AI00_AGENT_TEST_DB_URL is required: provision a dedicated MySQL/OceanBase "
                "database named with 'test' and grant its account DDL+DML"
            )
        pytest.skip("AI00_AGENT_TEST_DB_URL is not configured")
    parsed = urlparse(raw)
    database = parsed.path.lstrip("/")
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or "test" not in database.casefold():
        pytest.fail("AI00_AGENT_TEST_DB_URL must target an explicit dedicated database named with 'test'")
    return {
        "host": parsed.hostname, "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""), "password": unquote(parsed.password or ""),
        "database": database, "charset": "utf8mb4", "autocommit": False,
    }


@pytest.fixture(scope="module")
def mysql_factory():
    pymysql = pytest.importorskip("pymysql")
    params = _database_params()

    @contextmanager
    def factory():
        connection = pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **params)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS workmanship_app_skills ("
            "gid VARCHAR(191) PRIMARY KEY,owner_gid VARCHAR(191) NOT NULL,"
            "team_gid VARCHAR(191) NULL,scope VARCHAR(32) NOT NULL,status VARCHAR(32) NOT NULL,"
            "title VARCHAR(255) NULL,content JSON NULL,deleted_at DATETIME(6) NULL,"
            "updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) "
            "ON UPDATE CURRENT_TIMESTAMP(6)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        migration = (
            ROOT / "backend/db/migrations/domains/agent/0003_canvas_execution_control.sql"
        ).read_text(encoding="utf-8")
        for statement in migration.split(";"):
            if statement.strip():
                cursor.execute(statement)
    return factory


@pytest.fixture(autouse=True)
def isolated_rows(mysql_factory):
    with mysql_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE rr FROM workmanship_agent_canvas_runtime_results rr "
            "JOIN workmanship_agent_canvas_runs r ON r.run_id=rr.run_id WHERE r.team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        cursor.execute(
            "DELETE a FROM workmanship_agent_canvas_audit_events a "
            "JOIN workmanship_agent_canvas_runs r ON r.run_id=a.run_id WHERE r.team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        cursor.execute(
            "DELETE FROM workmanship_agent_canvas_invocations WHERE team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        cursor.execute(
            "DELETE FROM workmanship_agent_canvas_runs WHERE team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        cursor.execute("DELETE FROM workmanship_app_skills WHERE gid=%s", (SKILL_GID,))
        cursor.execute(
            "INSERT INTO workmanship_app_skills "
            "(gid,owner_gid,team_gid,scope,status,revision,title,content) "
            "VALUES (%s,%s,%s,'private','active',7,'SQL test',JSON_OBJECT('nodes',JSON_ARRAY()))",
            (SKILL_GID, PRINCIPAL.actor_gid, PRINCIPAL.team_gid),
        )
    yield


def _repository(factory):
    return AgentCapabilityRepository(factory, token_secret=TOKEN_SECRET)


def _coordinator(factory):
    return CanvasExecutionCoordinator(_repository(factory), token_secret=TOKEN_SECRET)


def _pause(factory, key="start-key"):
    repository = _repository(factory)
    coordinator = CanvasExecutionCoordinator(repository, token_secret=TOKEN_SECRET)
    accepted = coordinator.start(CanvasStartRequest(SKILL_GID, 7), PRINCIPAL, key)
    claim = repository.claim_next_canvas_invocation("pause-worker")
    repository.mark_canvas_invocation_dispatched(claim)
    pause_token = derive_canvas_token(TOKEN_SECRET, claim["run_id"], "pause", 1)
    paused = RuntimeDispatch(
        "paused", accepted.run_token, 1, pause_token=pause_token,
        halted_node_id="human-1", halted_label="Approve",
    )
    repository.record_canvas_runtime_result(
        claim["invocation_id"], claim["run_id"], PRINCIPAL, paused,
    )
    repository.complete_canvas_invocation(claim, paused)
    return repository, coordinator, accepted, pause_token


def _durable_json_values(factory):
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT request_json,result_json FROM workmanship_agent_canvas_invocations "
            "WHERE team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        invocations = cursor.fetchall()
        cursor.execute(
            "SELECT checkpoint_json,result_json FROM workmanship_agent_canvas_runs WHERE team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        runs = cursor.fetchall()
        cursor.execute(
            "SELECT result_json FROM workmanship_agent_canvas_runtime_results WHERE team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        runtime_results = cursor.fetchall()
    return [value for row in (*invocations, *runs, *runtime_results) for value in row.values() if value is not None]


def _assert_bearer_free(factory, *tokens):
    durable = "\n".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        for value in _durable_json_values(factory)
    )
    assert all(token not in durable for token in tokens)


def test_mysql_same_key_unique_race_replays_one_canonical_run(mysql_factory):
    barrier = threading.Barrier(2)

    def start():
        barrier.wait()
        return _coordinator(mysql_factory).start(
            CanvasStartRequest(SKILL_GID, 7), PRINCIPAL, "same-key",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = tuple(pool.map(lambda _index: start(), range(2)))

    assert first == second
    with mysql_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT (SELECT COUNT(*) FROM workmanship_agent_canvas_runs WHERE team_gid=%s) AS runs,"
            "(SELECT COUNT(*) FROM workmanship_agent_canvas_invocations WHERE team_gid=%s) AS invocations",
            (PRINCIPAL.team_gid, PRINCIPAL.team_gid),
        )
        assert cursor.fetchone() == {"runs": 1, "invocations": 1}


def test_mysql_skip_locked_claim_and_expired_lease_reclaim(mysql_factory):
    coordinator = _coordinator(mysql_factory)
    coordinator.start(CanvasStartRequest(SKILL_GID, 7), PRINCIPAL, "claim-1")
    coordinator.start(CanvasStartRequest(SKILL_GID, 7), PRINCIPAL, "claim-2")
    with mysql_factory() as lock_connection, lock_connection.cursor() as cursor:
        cursor.execute(
            "SELECT invocation_id FROM workmanship_agent_canvas_invocations "
            "WHERE team_gid=%s ORDER BY created_at,invocation_id LIMIT 1 FOR UPDATE",
            (PRINCIPAL.team_gid,),
        )
        locked_id = cursor.fetchone()["invocation_id"]
        claimed = _repository(mysql_factory).claim_next_canvas_invocation("skip-locked-worker")
        assert claimed["invocation_id"] != locked_id
    repository = _repository(mysql_factory)
    repository.mark_canvas_invocation_dispatched(claimed)
    with mysql_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE workmanship_agent_canvas_invocations SET status='completed' WHERE invocation_id=%s",
            (locked_id,),
        )
        cursor.execute(
            "UPDATE workmanship_agent_canvas_invocations SET lease_expires_at=%s WHERE invocation_id=%s",
            (datetime(2000, 1, 1, tzinfo=UTC).replace(tzinfo=None), claimed["invocation_id"]),
        )
    reclaimed = repository.claim_next_canvas_invocation("reclaim-worker")
    assert reclaimed["invocation_id"] == claimed["invocation_id"]
    assert reclaimed["reconcile"] is True


def test_mysql_resume_is_single_use_revision_bound_and_canonical(mysql_factory):
    repository, coordinator, accepted, pause_token = _pause(mysql_factory)
    request = CanvasResumeRequest(accepted.run_token, pause_token, 1, True)
    barrier = threading.Barrier(2)

    def resume(key):
        barrier.wait()
        try:
            return _coordinator(mysql_factory).resume(request, PRINCIPAL, key)
        except CapabilityBusinessError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(resume, ("resume-1", "resume-2")))
    winners = [value for value in outcomes if isinstance(value, RuntimeDispatch)]
    losers = [value for value in outcomes if isinstance(value, CapabilityBusinessError)]
    assert len(winners) == len(losers) == 1
    assert losers[0].code == "resource_not_found"
    winning_key = "resume-1" if isinstance(outcomes[0], RuntimeDispatch) else "resume-2"
    assert coordinator.resume(request, PRINCIPAL, winning_key) == winners[0]
    assert repository.load_canvas_execution_state(
        accepted.run_token, PRINCIPAL.actor_gid, PRINCIPAL.team_gid,
    )["revision"] == 2


def test_mysql_rollback_and_all_durable_json_are_bearer_free(mysql_factory):
    failing = _repository(mysql_factory)
    failing._canvas_audit = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected"))
    with pytest.raises(RuntimeError, match="injected"):
        CanvasExecutionCoordinator(failing, token_secret=TOKEN_SECRET).start(
            CanvasStartRequest(SKILL_GID, 7), PRINCIPAL, "rollback-key",
        )
    with mysql_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM workmanship_agent_canvas_runs WHERE team_gid=%s",
            (PRINCIPAL.team_gid,),
        )
        assert cursor.fetchone()["count"] == 0

    repository = _repository(mysql_factory)
    coordinator = CanvasExecutionCoordinator(repository, token_secret=TOKEN_SECRET)
    accepted = coordinator.start(
        CanvasStartRequest(SKILL_GID, 7), PRINCIPAL, "durable-start",
    )
    _assert_bearer_free(mysql_factory, accepted.run_token)
    claim = repository.claim_next_canvas_invocation("pause-worker")
    repository.mark_canvas_invocation_dispatched(claim)
    pause_token = derive_canvas_token(TOKEN_SECRET, claim["run_id"], "pause", 1)
    paused = RuntimeDispatch(
        "paused", accepted.run_token, 1, pause_token=pause_token,
        halted_node_id="human-1", halted_label="Approve",
    )
    repository.record_canvas_runtime_result(
        claim["invocation_id"], claim["run_id"], PRINCIPAL, paused,
    )
    repository.complete_canvas_invocation(claim, paused)
    _assert_bearer_free(mysql_factory, accepted.run_token, pause_token)
    paused_replay = coordinator.start(
        CanvasStartRequest(SKILL_GID, 7), PRINCIPAL, "durable-start",
    )
    assert paused_replay.pause_token == pause_token
    _assert_bearer_free(mysql_factory, accepted.run_token, pause_token)
    resume = CanvasResumeRequest(accepted.run_token, pause_token, 1, True)
    coordinator.resume(resume, PRINCIPAL, "durable-resume")
    _assert_bearer_free(mysql_factory, accepted.run_token, pause_token)
    claim = repository.claim_next_canvas_invocation("terminal-worker")
    repository.mark_canvas_invocation_dispatched(claim)
    terminal = RuntimeDispatch("completed", accepted.run_token, 2, summary="done")
    repository.record_canvas_runtime_result(
        claim["invocation_id"], claim["run_id"], PRINCIPAL, terminal,
    )
    repository.complete_canvas_invocation(claim, terminal)
    assert coordinator.resume(resume, PRINCIPAL, "durable-resume").status == "completed"
    _assert_bearer_free(mysql_factory, accepted.run_token, pause_token)
    state = repository.load_canvas_execution_for_invocation(
        claim["invocation_id"], PRINCIPAL.actor_gid, PRINCIPAL.team_gid,
    )
    assert all(
        token not in json.dumps(state, ensure_ascii=False, default=str)
        for token in (accepted.run_token, pause_token)
    )
