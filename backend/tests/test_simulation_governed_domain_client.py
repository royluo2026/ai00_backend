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
from backend.contracts.connector_execution_plan_v1 import canonical_hash
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


def test_scoped_execution_plan_is_filtered_by_governed_craft_work_package():
    class ExecutionClient(DomainClient):
        async def invoke(self, invocation, identity, correlation):
            self.calls.append((invocation, identity, correlation))
            if invocation.capability_id == "craft.bop.execution_structure.get":
                return SimpleNamespace(status=CapabilityStatus.COMPLETED, error=None, data={
                    "source": {"bop_version_gid": "bop-1", "revision": 1},
                    "content_hash": "sha256:" + "a" * 64,
                    "operations": [
                        {"operation_id": "op-line", "sequence": 1},
                        {"operation_id": "op-other", "sequence": 2},
                    ],
                })
            return SimpleNamespace(status=CapabilityStatus.COMPLETED, error=None, data={
                "scope": {"kind": "line", "gid": "line-1"},
                "work_items": [{"operation_id": "op-line"}],
            })

    adapter = GovernedSimulationRuntimeClient(Gateway())
    adapter.client = ExecutionClient()
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="user-1", authentication_method="test", authenticated_at=datetime(2026, 9, 3, tzinfo=UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="active"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="simulation-web"),
    )
    context = SimpleNamespace(effective_identity=identity, request_id="request-scope-1")

    result = asyncio.run(adapter.get_execution_plan({
        "version_gid": "bop-1", "scope": {"kind": "line", "gid": "line-1"},
    }, context))

    assert [item[0].capability_id for item in adapter.client.calls] == [
        "craft.bop.execution_structure.get", "craft.bop.work_package.get",
    ]
    assert [item["operation_id"] for item in result["operations"]] == ["op-line"]
    assert result["scope"] == {"kind": "line", "gid": "line-1"}


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


def test_connector_outcome_idempotency_is_stable_across_retry_attempts():
    adapter = GovernedSimulationRuntimeClient(Gateway())
    adapter.client = DomainClient()
    plan = ConnectorExecutionPlanV1.model_validate(VECTOR["plan"])
    outcome = completed_outcome()

    asyncio.run(adapter.apply_connector_outcome(plan, outcome, attempt=1))
    asyncio.run(adapter.apply_connector_outcome(plan, outcome, attempt=2))

    expected = f"{plan.plan_id}:{canonical_hash(outcome.model_dump(mode='json'))}"
    assert [call[0].idempotency_key for call in adapter.client.calls] == [
        expected, expected,
    ]
