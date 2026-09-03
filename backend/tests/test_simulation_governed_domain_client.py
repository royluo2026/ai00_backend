from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.capability_v2.contracts import (
    ActorIdentity, CapabilityStatus, ConsumerDescriptor, ConsumerIdentity,
    ConsumerType, TenantIdentity,
)
from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient
from backend.contracts.connector_execution_plan_v1 import ConnectorExecutionPlanV1
from backend.tests.test_connector_runtime_control_plane import VECTOR, completed_outcome


class Gateway:
    catalog_release = "rel_test"

    def __init__(self):
        self.approvals = []

    async def request_approval(self, envelope):
        raise AssertionError("Simulation must not self-issue downstream approval")


class DomainClient:
    def __init__(self):
        self.calls = []

    async def invoke(self, invocation, identity, correlation):
        self.calls.append((invocation, identity, correlation))
        if "plan" not in invocation.payload:
            return SimpleNamespace(
                status=CapabilityStatus.COMPLETED, error=None,
                data={"resource_id": invocation.payload.get("run_id"), "status": "applied"},
            )
        return SimpleNamespace(status=CapabilityStatus.COMPLETED, error=None, data={
            "operation_id": invocation.payload["plan"]["plan_id"],
            "status": "accepted", "version": 1,
        })


def test_connector_queue_uses_gateway_with_exact_payload_identity_approval_and_idempotency():
    gateway = Gateway()
    adapter = GovernedSimulationRuntimeClient(gateway)
    adapter.client = DomainClient()
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            user_id="user-1", authentication_method="test",
            authenticated_at=datetime(2026, 9, 3, tzinfo=UTC),
        ),
        tenant=TenantIdentity(tenant_id="team-1", membership="active"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="simulation-web"),
    )
    context = SimpleNamespace(effective_identity=identity, request_id="request-1")
    plan = ConnectorExecutionPlanV1.model_validate(VECTOR["plan"])

    result = asyncio.run(adapter.queue_plan(plan, context, approval_reference="approval_exact_1"))

    invocation, invoked_identity, correlation = adapter.client.calls[0]
    assert invocation.capability_id == "simulation.connector.plan.queue"
    assert invocation.major_version == 1
    assert invocation.payload == {"plan": plan.model_dump(mode="json")}
    assert invocation.idempotency_key == plan.plan_id
    assert invocation.approval_reference == "approval_exact_1"
    assert invoked_identity is identity
    assert correlation.request_id == "request-1"
    assert result["status"] == "accepted"


def test_connector_outcome_uses_local_runtime_identity_and_governed_simulation_projection():
    adapter = GovernedSimulationRuntimeClient(Gateway())
    adapter.client = DomainClient()
    plan = ConnectorExecutionPlanV1.model_validate(VECTOR["plan"])

    result = asyncio.run(adapter.apply_connector_outcome(plan, completed_outcome()))

    invocation, identity, correlation = adapter.client.calls[0]
    assert invocation.capability_id == "simulation.connector_materialization_outcome.apply"
    assert invocation.payload["run_id"] == plan.plan_id
    assert invocation.idempotency_key.startswith(plan.plan_id + ":")
    assert identity.actor.user_id == plan.user_id
    assert identity.tenant.tenant_id == plan.tenant_id
    assert identity.consumer.type is ConsumerType.LOCAL_RUNTIME
    assert identity.consumer.installation_id == plan.device_id
    assert correlation.request_id.startswith("connector-outcome-")
    assert result["status"] == "applied"
