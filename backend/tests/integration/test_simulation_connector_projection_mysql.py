"""Real MySQL/OceanBase recovery tests for the Simulation Connector outbox."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse
import uuid

import pytest

from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    canonical_hash,
)
from backend.tests.test_connector_runtime_control_plane import completed_outcome, plan
from plugins.simulation.simulation_backend.data.connector_repository import (
    ConnectorRepositoryError,
    SimulationConnectorRepository,
)


TEST_DB_URL = os.getenv("AI00_SIMULATION_TEST_DB_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="AI00_SIMULATION_TEST_DB_URL is required for real Connector recovery tests",
)


def _connect():
    import pymysql
    import pymysql.cursors

    parsed = urlparse(TEST_DB_URL)
    return pymysql.connect(
        host=parsed.hostname, port=parsed.port or 3306,
        user=unquote(parsed.username or ""), password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


@pytest.fixture(autouse=True)
def _simulation_database(monkeypatch):
    from plugins.simulation.simulation_backend.data import connection

    monkeypatch.setenv("AI00_SIMULATION_DB_URL", TEST_DB_URL)
    connection._pool = None
    ddl = (
        Path(__file__).resolve().parents[2]
        / "db/migrations/domains/simulation/0005_connector_control_plane.sql"
    ).read_text(encoding="utf-8")
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            for statement in (part.strip() for part in ddl.split(";")):
                if statement:
                    cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()
    yield
    connection._pool = None


def _unique_plan() -> ConnectorExecutionPlanV1:
    source = plan().model_dump(mode="json")
    source["plan_id"] = "plan-mysql-" + uuid.uuid4().hex
    source["device_id"] = "connector-mysql-" + uuid.uuid4().hex
    source["plan_hash"] = canonical_hash({key: value for key, value in source.items() if key != "plan_hash"})
    return ConnectorExecutionPlanV1.model_validate(source)


def _insert_leased(current: ConnectorExecutionPlanV1, lease_id: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_connector_plans "
                "(plan_id,connector_id,tenant_gid,user_gid,plan_hash,plan_json,status,lease_id,lease_until,expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,'leased',%s,DATE_ADD(NOW(6),INTERVAL 5 MINUTE),DATE_ADD(NOW(6),INTERVAL 10 MINUTE))",
                (
                    current.plan_id, current.device_id, current.tenant_id, current.user_id,
                    current.plan_hash, json.dumps(current.model_dump(mode="json")), lease_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _delete_plan(plan_id: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM workmanship_sim_connector_projection_outbox WHERE plan_id=%s",
                (plan_id,),
            )
            cursor.execute(
                "DELETE FROM workmanship_sim_connector_plans WHERE plan_id=%s",
                (plan_id,),
            )
        conn.commit()
    finally:
        conn.close()


def test_concurrent_completion_is_atomic_idempotent_and_conflict_safe():
    current = _unique_plan()
    lease_id = "lease-mysql-" + uuid.uuid4().hex
    outcome = completed_outcome().model_copy(update={"plan_id": current.plan_id})
    target = "simulation.connector_materialization_outcome.apply"
    _insert_leased(current, lease_id)
    try:
        def complete(value):
            return SimulationConnectorRepository().complete_with_projection_intent(
                current.device_id, current.plan_id, lease_id, value, target,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            intents = list(executor.map(complete, (outcome, outcome)))
        assert len({item.outcome_hash for item in intents}) == 1

        conflict = outcome.model_copy(update={"reported_at": outcome.reported_at + timedelta(seconds=1)})
        with pytest.raises(ConnectorRepositoryError, match="connector_outcome_conflict"):
            complete(conflict)

        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT outcome_hash FROM workmanship_sim_connector_plans WHERE plan_id=%s",
                    (current.plan_id,),
                )
                assert cursor.fetchone()["outcome_hash"] == canonical_hash(outcome.model_dump(mode="json"))
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM workmanship_sim_connector_projection_outbox WHERE plan_id=%s",
                    (current.plan_id,),
                )
                assert cursor.fetchone()["count"] == 1
        finally:
            conn.close()
    finally:
        _delete_plan(current.plan_id)


def test_claim_survives_connection_loss_and_stale_owner_cannot_finish():
    current = _unique_plan()
    lease_id = "lease-mysql-" + uuid.uuid4().hex
    outcome = completed_outcome().model_copy(update={"plan_id": current.plan_id})
    repository = SimulationConnectorRepository()
    _insert_leased(current, lease_id)
    try:
        repository.complete_with_projection_intent(
            current.device_id, current.plan_id, lease_id, outcome,
            "simulation.connector_materialization_outcome.apply",
        )
        first = repository.claim_projection("worker-old", 15)
        assert first is not None

        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE workmanship_sim_connector_projection_outbox "
                    "SET lease_until=DATE_SUB(NOW(6),INTERVAL 1 SECOND) WHERE plan_id=%s",
                    (current.plan_id,),
                )
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(ConnectorRepositoryError, match="projection_lease_invalid"):
            repository.finish_projection(current.plan_id, "worker-old")
        assert repository.reclaim_stale_projections() == 1
        second = repository.claim_projection("worker-new", 15)
        assert second is not None and second.attempt == first.attempt + 1
        with pytest.raises(ConnectorRepositoryError, match="projection_lease_invalid"):
            repository.finish_projection(current.plan_id, "worker-old")
        repository.finish_projection(current.plan_id, "worker-new")
    finally:
        _delete_plan(current.plan_id)
