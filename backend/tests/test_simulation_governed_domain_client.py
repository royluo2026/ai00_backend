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
from backend.tests.test_connector_runtime_control_plane import VECTOR


class Gateway:
    catalog_release = "rel_test"

    def __init__(self):
        self.approvals = []

    async def request_approval(self, envelope):
        self.approvals.append(envelope)
        return SimpleNamespace(token="approval_exact_1")


class DomainClient:
    def __init__(self):
        self.calls = []

    async def invoke(self, invocation, identity, correlation):
        self.calls.append((invocation, identity, correlation))
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

    result = asyncio.run(adapter.queue_plan(plan, context))

    approval = gateway.approvals[0]
    invocation, invoked_identity, correlation = adapter.client.calls[0]
    assert approval.capability_id == invocation.capability_id == "device.connector.plan.queue"
    assert approval.payload == invocation.payload == {"plan": plan.model_dump(mode="json")}
    assert approval.idempotency_key == invocation.idempotency_key == plan.plan_id
    assert invocation.approval_reference == "approval_exact_1"
    assert invoked_identity is identity
    assert correlation.request_id == "request-1"
    assert result["status"] == "accepted"
