from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from backend.tests.test_connector_runtime_control_plane import completed_outcome, plan
from plugins.simulation.simulation_backend.application.connector_projection_worker import (
    ConnectorProjectionWorker,
)
from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient


def test_targeted_projection_claim_does_not_take_an_older_plan(monkeypatch):
    from plugins.simulation.simulation_backend.data import connector_repository as module
    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=None):
            if sql.startswith('SELECT'):
                self.selected = params[0] if params else 'older-plan'
        def fetchone(self):
            return dict(plan_id=self.selected, outcome_hash='a'*64,
                        target_capability='simulation.connector_document_snapshot_outcome.apply', attempt=0)
    cursor = Cursor()
    @contextmanager
    def connect(): yield SimpleNamespace(cursor=lambda: cursor)
    monkeypatch.setattr(module, 'get_simulation_conn', connect)
    targeted = module.SimulationConnectorRepository(projection_protocol='ai00.connector.execution-plan.v2',
                                                    projection_plan_id='current-snapshot')
    assert targeted.claim_projection('test-worker').plan_id == 'current-snapshot'
    assert module.SimulationConnectorRepository().claim_projection('test-worker').plan_id == 'older-plan'


class Repository:
    def __init__(self):
        self.finished = []
        self.failed = []
        self.reclaimed = 0
        self.lease = SimpleNamespace(
            plan_id="plan-001", outcome_hash="sha256:" + "a" * 64,
            target_capability="simulation.connector_materialization_outcome.apply",
            attempt=3, owner="worker-1",
        )

    def reclaim_stale_projections(self):
        self.reclaimed += 1

    def claim_projection(self, owner, lease_seconds):
        assert owner == "worker-1"
        assert lease_seconds == 45
        return self.lease

    def read_projection_payload(self, lease):
        assert lease is self.lease
        return plan(), completed_outcome()

    def finish_projection(self, plan_id, owner):
        self.finished.append((plan_id, owner))

    def fail_projection(self, plan_id, owner, **failure):
        self.failed.append((plan_id, owner, failure))


class Projector:
    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure

    @staticmethod
    def target(_plan):
        return "simulation.connector_materialization_outcome.apply"

    async def apply(self, current_plan, outcome, *, attempt):
        self.calls.append((current_plan.plan_id, outcome.plan_id, attempt))
        if self.failure:
            raise self.failure


def test_production_projector_implements_worker_port():
    """The exact projector composed by the CLI must satisfy the worker port."""
    assert callable(getattr(GovernedSimulationRuntimeClient, "target", None))
    assert asyncio.iscoroutinefunction(
        getattr(GovernedSimulationRuntimeClient, "apply", None)
    )


def test_worker_reclaims_claims_projects_and_finishes_by_lease_owner():
    repository = Repository()
    projector = Projector()
    worker = ConnectorProjectionWorker(
        repository, projector, owner="worker-1", lease_seconds=45,
    )

    assert asyncio.run(worker.run_once()) is True
    assert repository.reclaimed == 1
    assert projector.calls == [("plan-001", "plan-001", 3)]
    assert repository.finished == [("plan-001", "worker-1")]
    assert repository.failed == []


def test_worker_records_retryable_failure_without_losing_intent():
    failure = RuntimeError("gateway_unavailable")
    failure.retryable = True
    repository = Repository()
    worker = ConnectorProjectionWorker(
        repository, Projector(failure=failure), owner="worker-1", lease_seconds=45,
    )

    assert asyncio.run(worker.run_once()) is True
    assert repository.finished == []
    assert repository.failed == [(
        "plan-001", "worker-1",
        {"error_code": "gateway_unavailable", "retryable": True},
    )]
