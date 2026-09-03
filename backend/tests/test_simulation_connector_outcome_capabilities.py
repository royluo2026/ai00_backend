from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

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
from plugins.simulation.simulation_backend.capabilities.connector_outcomes import (
    ConnectorOutcomeProvider,
)
from plugins.simulation.simulation_backend.capabilities.provider import register
from plugins.simulation.simulation_backend.capabilities.connector_outcomes import specs
from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient


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
