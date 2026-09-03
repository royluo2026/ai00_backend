from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from contextlib import contextmanager

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorPlanOutcomeV1,
    ConnectorStepResultV1,
    canonical_hash,
)
from backend.tests.test_simulation_capture_workflow import ARTIFACT, _context, _workflow
from backend.tests.test_connector_runtime_control_plane import completed_outcome
from plugins.simulation.simulation_backend.capabilities.connector_outcomes import (
    ConnectorOutcomeProvider,
)
from plugins.simulation.simulation_backend.capabilities.provider import register
from plugins.simulation.simulation_backend.capabilities.connector_outcomes import specs
from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient
from plugins.simulation.simulation_backend.data.connector_repository import (
    SimulationConnectorRepository,
)


def test_capture_outcome_is_projected_only_through_its_exact_simulation_resource():
    workflow, repository, connector, _ = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    asyncio.run(workflow.dispatch_next("run-1", "approval-device", _context()))
    plan = connector.plans[0][0]
    now = datetime(2026, 9, 3, tzinfo=UTC)
    results = []
    for step in plan.steps:
        value = {"artifact": ARTIFACT} if step.operation_id == "vismockup.view.capture@1" else {}
        results.append(ConnectorStepResultV1(
            step_id=step.step_id, status="completed", result=value,
            result_hash=canonical_hash(value), started_at=now, completed_at=now,
        ))
    outcome = ConnectorPlanOutcomeV1(
        protocol=plan.protocol, plan_id=plan.plan_id, status="completed",
        steps=tuple(results), reported_at=now,
    )
    provider = ConnectorOutcomeProvider(workflow, snapshot_workflow=None)
    payload = {
        "capture_run_id": "run-1",
        "plan_json": json.dumps(plan.model_dump(mode="json")),
        "outcome_json": json.dumps(outcome.model_dump(mode="json")),
    }

    result = asyncio.run(provider.apply_capture(payload, CapabilityContext(
        user_gid="user-1", team_gid="team-1", source="connector",
    )))

    assert result.data == {"resource_id": "run-1", "status": "applied"}
    assert repository.runs["run-1"]["steps"][0]["status"] == "completed"


def test_empty_unknown_capture_outcome_stops_the_serial_workflow():
    workflow, repository, connector, _ = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    asyncio.run(workflow.dispatch_next("run-1", "approval-device", _context()))
    plan = connector.plans[0][0]
    outcome = ConnectorPlanOutcomeV1(
        protocol=plan.protocol, plan_id=plan.plan_id,
        status="outcome_unknown", steps=(),
        reported_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    asyncio.run(ConnectorOutcomeProvider(workflow, None).apply_capture({
        "capture_run_id": "run-1",
        "plan_json": json.dumps(plan.model_dump(mode="json")),
        "outcome_json": json.dumps(outcome.model_dump(mode="json")),
    }, _context()))

    assert repository.runs["run-1"]["status"] == "outcome_unknown"
    assert repository.runs["run-1"]["steps"][0]["status"] == "outcome_unknown"
    assert workflow.next_action("run-1", _context()) is None


def test_authenticated_connector_outcome_reaches_simulation_through_real_gateway(monkeypatch):
    from backend.routers import deps

    workflow, repository, connector, _ = _workflow()
    asyncio.run(workflow.start_capture("env-1", 1, "device-1", _context()))
    asyncio.run(workflow.dispatch_next("run-1", "approval-device", _context()))
    plan = connector.plans[0][0]
    outcome = ConnectorPlanOutcomeV1(
        protocol=plan.protocol, plan_id=plan.plan_id,
        status="outcome_unknown", steps=(),
        reported_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    registry = CapabilityRegistry()
    for spec, handler in specs(ConnectorOutcomeProvider(workflow, None)):
        register(registry, spec, handler)
    descriptor = registry.get("simulation.connector_capture_outcome.apply", 1).descriptor
    release = build_release([descriptor])
    catalog_store = InMemoryCatalogStore(); catalog_store.publish(release)
    monkeypatch.setattr(deps, "build_profile", lambda _user: {
        "permissions": ["simulation.use"], "org_role": "member", "grants": [],
    })
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda user_id: {"gid": user_id, "is_active": True},
        grants_resolver=lambda identity, user: deps.build_capability_authorization_grants(
            user, identity.tenant.tenant_id, identity.consumer.type.value, identity,
        ),
        resource_authorizer=lambda ref, identity, user: ref == "simulation-capture-run:run-1",
    )
    gateway = CapabilityGatewayService(
        CatalogResolver(catalog_store, registry), policy,
        reliability=ReliabilityCoordinator(
            InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100),
        ),
    ).bind_release(release.release_id)

    result = asyncio.run(GovernedSimulationRuntimeClient(gateway).apply_connector_outcome(
        plan, outcome, attempt=1,
    ))

    assert result == {"resource_id": "run-1", "status": "applied"}
    assert repository.runs["run-1"]["status"] == "outcome_unknown"


class _ProjectionCursor:
    def __init__(self, *, fail_insert: bool = False):
        self.executed = []
        self.rowcount = 1
        self.fail_insert = fail_insert

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))
        if self.fail_insert and "connector_projection_outbox" in sql and sql.lstrip().startswith("INSERT"):
            raise RuntimeError("outbox_insert_failed")

    def fetchone(self):
        return {
            "status": "leased",
            "outcome_hash": None,
            "outcome_json": None,
        }


class _ClaimCursor(_ProjectionCursor):
    def __init__(self, *, rowcount: int = 1):
        super().__init__()
        self.rowcount = rowcount

    def fetchone(self):
        return {
            "plan_id": "plan-001",
            "outcome_hash": "sha256:" + "a" * 64,
            "target_capability": "simulation.connector_materialization_outcome.apply",
            "attempt": 2,
        }


class _ProjectionConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor


def _transaction(connection):
    @contextmanager
    def current():
        try:
            yield connection
            connection.commits += 1
        except Exception:
            connection.rollbacks += 1
            raise
    return current


def test_completion_and_durable_projection_intent_share_one_transaction(monkeypatch):
    from plugins.simulation.simulation_backend.data import connector_repository as module

    cursor = _ProjectionCursor()
    connection = _ProjectionConnection(cursor)
    monkeypatch.setattr(module, "get_simulation_conn", _transaction(connection))
    outcome = completed_outcome()

    intent = SimulationConnectorRepository().complete_with_projection_intent(
        "device-001", "plan-001", "lease-1", outcome,
        "simulation.connector_materialization_outcome.apply",
    )

    statements = [sql for sql, _params in cursor.executed]
    assert connection.commits == 1
    assert any(sql.startswith("UPDATE workmanship_sim_connector_plans") for sql in statements)
    assert any(sql.startswith("INSERT INTO workmanship_sim_connector_projection_outbox") for sql in statements)
    assert intent.outcome_hash == canonical_hash(outcome.model_dump(mode="json"))
    assert intent.status == "pending"


def test_outbox_failure_rolls_back_plan_completion(monkeypatch):
    from plugins.simulation.simulation_backend.data import connector_repository as module

    cursor = _ProjectionCursor(fail_insert=True)
    connection = _ProjectionConnection(cursor)
    monkeypatch.setattr(module, "get_simulation_conn", _transaction(connection))

    try:
        SimulationConnectorRepository().complete_with_projection_intent(
            "device-001", "plan-001", "lease-1", completed_outcome(),
            "simulation.connector_materialization_outcome.apply",
        )
    except RuntimeError as exc:
        assert str(exc) == "outbox_insert_failed"
    else:
        raise AssertionError("outbox failure must escape the transaction")

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_projection_claim_uses_owner_lease_and_increments_attempt(monkeypatch):
    from plugins.simulation.simulation_backend.data import connector_repository as module

    cursor = _ClaimCursor()
    connection = _ProjectionConnection(cursor)
    monkeypatch.setattr(module, "get_simulation_conn", _transaction(connection))

    lease = SimulationConnectorRepository().claim_projection("worker-1", 45)

    assert lease is not None
    assert lease.owner == "worker-1"
    assert lease.attempt == 3
    statements = [sql for sql, _params in cursor.executed]
    assert "FOR UPDATE SKIP LOCKED" in statements[0]
    assert "lease_owner=%s" in statements[1]
    assert "lease_until=DATE_ADD(NOW(6),INTERVAL %s SECOND)" in statements[1]


def test_stale_projection_owner_cannot_finish(monkeypatch):
    from plugins.simulation.simulation_backend.data import connector_repository as module

    cursor = _ClaimCursor(rowcount=0)
    connection = _ProjectionConnection(cursor)
    monkeypatch.setattr(module, "get_simulation_conn", _transaction(connection))

    with pytest.raises(RuntimeError, match="projection_lease_invalid"):
        SimulationConnectorRepository().finish_projection("plan-001", "stale-worker")


def test_expired_projection_claims_are_reclaimed(monkeypatch):
    from plugins.simulation.simulation_backend.data import connector_repository as module

    cursor = _ClaimCursor(rowcount=2)
    connection = _ProjectionConnection(cursor)
    monkeypatch.setattr(module, "get_simulation_conn", _transaction(connection))

    reclaimed = SimulationConnectorRepository().reclaim_stale_projections(
        datetime(2026, 9, 3, tzinfo=UTC),
    )

    assert reclaimed == 2
    statement = cursor.executed[0][0]
    assert "status='projecting'" in statement
    assert "lease_until<=%s" in statement
    assert "status='retryable_failed'" in statement
