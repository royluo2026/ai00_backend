"""Governed cross-domain client used by Simulation orchestration."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from threading import RLock
from typing import Any

from backend.capability_v2.contracts import (
    ActorIdentity, CapabilityStatus, ConsumerDescriptor, ConsumerIdentity,
    ConsumerType, CorrelationRef, TenantIdentity,
)
from backend.capability_v2.domain_client import DomainCapabilityClient, DomainInvocation
from backend.capability_v2.provider_contracts import CapabilityBusinessError


class SimulationRuntimePorts:
    def __init__(self) -> None:
        self._ports: dict[str, Any] = {}
        self._lock = RLock()

    def register(self, name: str, port: Any) -> None:
        with self._lock:
            current = self._ports.get(name)
            if current is not None and (
                type(current).__module__, type(current).__qualname__
            ) != (type(port).__module__, type(port).__qualname__):
                raise RuntimeError(f"simulation runtime port already registered: {name}")
            self._ports[name] = port

    def require(self, name: str) -> Any:
        with self._lock:
            port = self._ports.get(name)
        if port is None:
            raise RuntimeError(f"simulation runtime port unavailable: {name}")
        return port


simulation_runtime_ports = SimulationRuntimePorts()


class GovernedSimulationRuntimeClient:
    """Routes every owner-domain operation through the bound Capability Gateway."""

    def __init__(self, gateway) -> None:
        self.gateway = gateway
        self.client = DomainCapabilityClient(gateway)

    @staticmethod
    def _identity(context):
        identity = getattr(context, "effective_identity", None)
        if identity is None:
            raise CapabilityBusinessError(
                "delegation_required", "A Gateway-derived effective identity is required."
            )
        return identity

    @staticmethod
    def _correlation(context) -> CorrelationRef:
        request_id = str(getattr(context, "request_id", "") or "")
        if not request_id:
            raise CapabilityBusinessError("request_identity_required", "A request id is required.")
        return CorrelationRef(request_id=request_id, trace_id=request_id)

    async def _invoke(self, invocation: DomainInvocation, context):
        identity = self._identity(context)
        correlation = self._correlation(context)
        result = await self.client.invoke(invocation, identity, correlation)
        if result.status is not CapabilityStatus.COMPLETED or result.error is not None:
            error = result.error
            raise CapabilityBusinessError(
                error.code if error else "downstream_capability_failed",
                error.message if error else "The downstream capability did not complete.",
                retryable=bool(error and error.retryable),
            )
        return result.data

    async def get_execution_plan(self, reference, context):
        return await self._invoke(DomainInvocation(
            "craft.bop.execution_structure.get", 1,
            {"version_gid": str(reference["version_gid"])},
        ), context)

    async def resolve_resource_models(self, items, context):
        return await self._invoke(DomainInvocation(
            "knowledge.resource_model_mapping.resolve", 1, {"items": list(items)},
        ), context)

    async def get_health(self, device_id, context):
        return await self._invoke(DomainInvocation(
            "simulation.connector.health.get", 1, {"connector_id": device_id},
        ), context)

    async def queue_plan(self, plan, context, *, approval_reference):
        return await self._invoke(DomainInvocation(
            "simulation.connector.plan.queue", 1,
            {"plan": plan.model_dump(mode="json")}, idempotency_key=plan.plan_id,
            approval_reference=approval_reference,
        ), context)

    async def attach_screenshot(self, *, context, approval_reference, **payload):
        key = f"{payload['capture_run_id']}:{payload['operation_id']}"
        return await self._invoke(DomainInvocation(
            "craft.process_screenshot.attach", 1, payload, idempotency_key=key,
            approval_reference=approval_reference,
        ), context)

    @staticmethod
    def connector_outcome_target(plan):
        operations = {step.operation_id for step in plan.steps}
        if operations == {"vismockup.document.snapshot@1"}:
            capability_id = "simulation.connector_document_snapshot_outcome.apply"
            resource_payload = {"snapshot_request_id": plan.plan_id}
        elif "vismockup.view.capture@1" in operations:
            capture_steps = [
                step for step in plan.steps if step.operation_id == "vismockup.view.capture@1"
            ]
            capture_run_id = str(capture_steps[0].payload.get("capture_run_id") or "") if len(capture_steps) == 1 else ""
            capability_id = "simulation.connector_capture_outcome.apply"
            resource_payload = {"capture_run_id": capture_run_id}
        else:
            capability_id = "simulation.connector_materialization_outcome.apply"
            resource_payload = {"run_id": plan.plan_id}
        return capability_id, resource_payload

    async def apply_connector_outcome(self, plan, outcome, *, attempt=1):
        capability_id, resource_payload = self.connector_outcome_target(plan)
        outcome_value = outcome.model_dump(mode="json")
        payload = {
            **resource_payload,
            "plan_json": json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
            "outcome_json": json.dumps(outcome_value, sort_keys=True, separators=(",", ":")),
        }
        digest = hashlib.sha256(
            payload["outcome_json"].encode("utf-8")
        ).hexdigest()
        identity = ConsumerIdentity(
            actor=ActorIdentity(
                user_id=plan.user_id,
                authentication_method="connector_plan_lease",
                authenticated_at=plan.issued_at,
            ),
            tenant=TenantIdentity(tenant_id=plan.tenant_id, membership="member"),
            consumer=ConsumerDescriptor(
                type=ConsumerType.LOCAL_RUNTIME,
                consumer_id="ai00.connector",
                installation_id=plan.device_id,
            ),
        )
        correlation = CorrelationRef(
            request_id=f"connector-outcome-{digest}",
            trace_id=f"connector-plan-{plan.plan_id}",
        )
        result = await self.client.invoke(DomainInvocation(
            capability_id, 1, payload,
            idempotency_key=f"{plan.plan_id}:{digest}:{attempt}",
        ), identity, correlation)
        if result.status is not CapabilityStatus.COMPLETED or result.error is not None:
            error = result.error
            raise CapabilityBusinessError(
                error.code if error else "downstream_capability_failed",
                error.message if error else "The Connector outcome projection did not complete.",
                retryable=bool(error and error.retryable),
            )
        return result.data


def configure_simulation_runtime_gateway(gateway) -> None:
    client = GovernedSimulationRuntimeClient(gateway)
    simulation_runtime_ports.register("governed.domain_client", client)
    simulation_runtime_ports.register("simulation.connector_outcome", client)


class CraftExecutionPlanPortProxy:
    async def get_execution_plan(self, reference, context):
        return await simulation_runtime_ports.require("governed.domain_client").get_execution_plan(reference, context)


class CraftScreenshotPortProxy:
    async def attach_screenshot(self, **kwargs):
        return await simulation_runtime_ports.require("governed.domain_client").attach_screenshot(**kwargs)


class ConnectorPortProxy:
    async def get_health(self, device_id, context):
        return await simulation_runtime_ports.require("governed.domain_client").get_health(device_id, context)

    async def queue_plan(self, plan, context, *, approval_reference):
        return await simulation_runtime_ports.require("governed.domain_client").queue_plan(
            plan, context, approval_reference=approval_reference,
        )


class ConnectorOutcomePortProxy:
    def target(self, plan):
        return GovernedSimulationRuntimeClient.connector_outcome_target(plan)[0]

    async def apply(self, plan, outcome, *, attempt=1):
        return await simulation_runtime_ports.require("simulation.connector_outcome").apply_connector_outcome(
            plan, outcome, attempt=attempt,
        )


class KnowledgeMappingPortProxy:
    async def resolve_resource_models(self, items, context):
        return await simulation_runtime_ports.require("governed.domain_client").resolve_resource_models(items, context)


__all__ = [
    "ConnectorOutcomePortProxy", "ConnectorPortProxy", "CraftExecutionPlanPortProxy", "CraftScreenshotPortProxy",
    "GovernedSimulationRuntimeClient", "KnowledgeMappingPortProxy", "SimulationRuntimePorts",
    "configure_simulation_runtime_gateway", "simulation_runtime_ports",
]
