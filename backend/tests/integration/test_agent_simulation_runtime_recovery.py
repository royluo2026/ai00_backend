"""Live recovery coverage for the Agent and Simulation durable workers."""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from types import SimpleNamespace

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.contracts import (
    CapabilityErrorV2,
    CapabilityResultV2,
    CapabilityStatus,
    CorrelationRef,
    SideEffectLevel,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import SqlOutcomeStore
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    canonical_hash,
)
from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient
from backend.tests.test_connector_runtime_control_plane import completed_outcome, plan
from plugins.agent.agent_backend.infrastructure.capability_outbox import (
    AgentCapabilityOutboxDispatcher,
    AgentCapabilityOutboxRepository,
)
from plugins.simulation.simulation_backend.application.connector_projection_worker import (
    ConnectorProjectionWorker,
)
from plugins.simulation.simulation_backend.data.connector_repository import (
    SimulationConnectorRepository,
)


pytestmark = pytest.mark.integration


def _row(factory, sql: str, params=()):
    with factory() as conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def _unique_plan() -> ConnectorExecutionPlanV1:
    value = plan().model_dump(mode="json")
    value["plan_id"] = "plan-p0-" + uuid.uuid4().hex
    value["device_id"] = "connector-p0-" + uuid.uuid4().hex
    value["plan_hash"] = canonical_hash(
        {key: item for key, item in value.items() if key != "plan_hash"}
    )
    return ConnectorExecutionPlanV1.model_validate(value)


def test_agent_lifespan_reconciles_committed_outbox_once(base_db, agent_db):
    """A committed Agent event converges through the production lifecycle once."""
    token = uuid.uuid4().hex
    operation_id = "op_" + token
    request_id = "req-p0-" + token
    event_id = "evt-p0-" + token
    payload = {"data": {"interaction_id": "interaction-p0-" + token}, "evidence": []}
    with base_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO workmanship_base_capability_outcomes "
            "(operation_id,request_id,idempotency_scope,payload_hash,capability_id,major_version,"
            "tenant_id,consumer_scope,actor_id,consumer_type,consumer_id,policy_version,status,started_at) "
            "VALUES (%s,%s,%s,%s,'agent.interaction.request',1,'tenant-p0','web:user-p0',"
            "'user-p0','web','ai00.web.agent','integration-p0','outcome_unknown',NOW(6))",
            (operation_id, request_id, "idem-p0-" + token, "sha256:" + "a" * 64),
        )
    with agent_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO workmanship_agent_capability_outbox "
            "(event_id,operation_id,outcome_operation_id,async_operation_id,request_id,"
            "capability_id,major_version,payload_json,state) "
            "VALUES (%s,'',%s,NULL,%s,'agent.interaction.request',1,%s,'pending')",
            (event_id, operation_id, request_id, json.dumps(payload)),
        )

    gateway = CapabilityGatewayService(
        SimpleNamespace(),
        reliability=ReliabilityCoordinator(
            SqlOutcomeStore(base_db), InMemoryRateLimiter(limit=100)
        ),
    )
    dispatcher = AgentCapabilityOutboxDispatcher(
        AgentCapabilityOutboxRepository(agent_db),
        gateway.reconcile_committed_agent_outcome,
        poll_interval=0.05,
        worker_id="integration-p0-agent",
    )
    registry = CapabilityRegistry()
    registry.register_lifecycle(
        "agent.capability-outbox",
        dispatcher.start,
        dispatcher.stop,
        health=lambda: dispatcher.health,
    )

    async def exercise():
        await registry.start_lifecycles()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                current = _row(
                    agent_db,
                    "SELECT state FROM workmanship_agent_capability_outbox WHERE event_id=%s",
                    (event_id,),
                )
                if current and current["state"] == "delivered":
                    return
                await asyncio.sleep(0.1)
            raise AssertionError("Agent outbox did not converge before the deadline")
        finally:
            await registry.stop_lifecycles()

    try:
        asyncio.run(exercise())
        assert registry.lifecycle_health("agent.capability-outbox")["status"] == "stopped"
        assert _row(
            base_db,
            "SELECT status FROM workmanship_base_capability_outcomes WHERE operation_id=%s",
            (operation_id,),
        )["status"] == "completed"
        assert _row(
            base_db,
            "SELECT COUNT(*) AS count FROM workmanship_base_capability_audit_outbox WHERE operation_id=%s",
            (operation_id,),
        )["count"] == 1
        gateway.reconcile_committed_agent_outcome({
            "outcome_operation_id": operation_id,
            "request_id": request_id,
            "capability_id": "agent.interaction.request",
            "major_version": 1,
            "payload": payload,
        })
        assert _row(
            base_db,
            "SELECT COUNT(*) AS count FROM workmanship_base_capability_audit_outbox WHERE operation_id=%s",
            (operation_id,),
        )["count"] == 1
    finally:
        with agent_db() as conn, conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM workmanship_agent_capability_outbox WHERE event_id=%s",
                (event_id,),
            )
        with base_db() as conn, conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM workmanship_base_capability_audit_outbox WHERE operation_id=%s",
                (operation_id,),
            )
            cursor.execute(
                "DELETE FROM workmanship_base_capability_outcomes WHERE operation_id=%s",
                (operation_id,),
            )


class _ProjectionCatalog:
    @staticmethod
    def descriptor(_capability_id, _major_version):
        return SimpleNamespace(
            side_effect_level=SideEffectLevel.REVERSIBLE_WRITE,
            idempotency_policy="required",
        )


class _FailOnceProjectionGateway:
    catalog_release = "integration-p0"

    def __init__(self):
        self.calls = 0
        self.completed = 0

    @staticmethod
    def catalog(_release_id):
        return _ProjectionCatalog()

    async def invoke(self, envelope):
        self.calls += 1
        if self.calls == 1:
            return CapabilityResultV2(
                ok=False,
                status=CapabilityStatus.FAILED,
                capability_id=envelope.capability_id,
                major_version=envelope.major_version,
                error=CapabilityErrorV2(
                    code="integration_gateway_unavailable",
                    message="forced first projection failure",
                    retryable=True,
                ),
                correlation=CorrelationRef(request_id=envelope.request_id),
            )
        self.completed += 1
        return CapabilityResultV2(
            ok=True,
            status=CapabilityStatus.COMPLETED,
            capability_id=envelope.capability_id,
            major_version=envelope.major_version,
            data={"projected": True},
            correlation=CorrelationRef(request_id=envelope.request_id),
        )


def test_simulation_projection_recovers_without_duplicate_effect(
    simulation_db, monkeypatch
):
    """A failed Simulation projection retries without duplicating its effect."""
    from plugins.simulation.simulation_backend.data import connection

    monkeypatch.setenv(
        "AI00_SIMULATION_DB_URL", os.environ["AI00_SIMULATION_TEST_DB_URL"]
    )
    connection._pool = None
    current = _unique_plan()
    lease_id = "lease-p0-" + uuid.uuid4().hex
    outcome = completed_outcome().model_copy(update={"plan_id": current.plan_id})
    repository = SimulationConnectorRepository()
    with simulation_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO workmanship_sim_connector_plans "
            "(plan_id,connector_id,tenant_gid,user_gid,plan_hash,plan_json,status,lease_id,lease_until,expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,'leased',%s,DATE_ADD(NOW(6),INTERVAL 5 MINUTE),"
            "DATE_ADD(NOW(6),INTERVAL 10 MINUTE))",
            (
                current.plan_id,
                current.device_id,
                current.tenant_id,
                current.user_id,
                current.plan_hash,
                json.dumps(current.model_dump(mode="json")),
                lease_id,
            ),
        )
    repository.complete_with_projection_intent(
        current.device_id,
        current.plan_id,
        lease_id,
        outcome,
        "simulation.connector_materialization_outcome.apply",
    )
    gateway = _FailOnceProjectionGateway()
    worker = ConnectorProjectionWorker(
        repository,
        GovernedSimulationRuntimeClient(gateway),
        owner="integration-p0-simulation",
        lease_seconds=15,
    )
    try:
        assert asyncio.run(worker.run_once()) is True
        assert _row(
            simulation_db,
            "SELECT status FROM workmanship_sim_connector_projection_outbox WHERE plan_id=%s",
            (current.plan_id,),
        )["status"] == "retryable_failed"
        with simulation_db() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_connector_projection_outbox "
                "SET next_retry_at=DATE_SUB(NOW(6),INTERVAL 1 SECOND) WHERE plan_id=%s",
                (current.plan_id,),
            )
        assert asyncio.run(worker.run_once()) is True
        assert asyncio.run(worker.run_once()) is False
        result = _row(
            simulation_db,
            "SELECT status,attempt FROM workmanship_sim_connector_projection_outbox WHERE plan_id=%s",
            (current.plan_id,),
        )
        assert result == {"status": "projected", "attempt": 2}
        assert gateway.calls == 2
        assert gateway.completed == 1
    finally:
        with simulation_db() as conn, conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM workmanship_sim_connector_projection_outbox WHERE plan_id=%s",
                (current.plan_id,),
            )
            cursor.execute(
                "DELETE FROM workmanship_sim_connector_plans WHERE plan_id=%s",
                (current.plan_id,),
            )
        connection._pool = None
