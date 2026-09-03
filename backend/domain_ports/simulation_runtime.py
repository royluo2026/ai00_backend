"""Governed cross-domain client used by Simulation orchestration."""
from __future__ import annotations

from threading import RLock
from typing import Any

from backend.capability_v2.contracts import (
    CapabilityStatus, CorrelationRef, InvocationEnvelope,
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

    def _envelope(self, invocation, identity, correlation) -> InvocationEnvelope:
        return InvocationEnvelope(
            capability_id=invocation.capability_id,
            major_version=invocation.major_version,
            catalog_release=self.gateway.catalog_release,
            payload=dict(invocation.payload),
            identity=identity,
            idempotency_key=invocation.idempotency_key,
            expected_resource_version=invocation.expected_resource_version,
            request_id=correlation.request_id,
            trace_id=correlation.trace_id or correlation.request_id,
        )

    async def _invoke(self, invocation: DomainInvocation, context, *, confirm=False):
        identity = self._identity(context)
        correlation = self._correlation(context)
        if confirm:
            issued = await self.gateway.request_approval(
                self._envelope(invocation, identity, correlation)
            )
            invocation = DomainInvocation(
                capability_id=invocation.capability_id,
                major_version=invocation.major_version,
                payload=invocation.payload,
                idempotency_key=invocation.idempotency_key,
                expected_resource_version=invocation.expected_resource_version,
                approval_reference=issued.token,
            )
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
            "device.connector.health.get", 1, {"device_id": device_id},
        ), context)

    async def queue_plan(self, plan, context):
        return await self._invoke(DomainInvocation(
            "device.connector.plan.queue", 1,
            {"plan": plan.model_dump(mode="json")}, idempotency_key=plan.plan_id,
        ), context, confirm=True)

    async def attach_screenshot(self, *, context, **payload):
        key = f"{payload['capture_run_id']}:{payload['operation_id']}"
        return await self._invoke(DomainInvocation(
            "craft.process_screenshot.attach", 1, payload, idempotency_key=key,
        ), context, confirm=True)


def configure_simulation_runtime_gateway(gateway) -> None:
    client = GovernedSimulationRuntimeClient(gateway)
    simulation_runtime_ports.register("governed.domain_client", client)


class CraftExecutionPlanPortProxy:
    async def get_execution_plan(self, reference, context):
        return await simulation_runtime_ports.require("governed.domain_client").get_execution_plan(reference, context)


class CraftScreenshotPortProxy:
    async def attach_screenshot(self, **kwargs):
        return await simulation_runtime_ports.require("governed.domain_client").attach_screenshot(**kwargs)


class ConnectorPortProxy:
    async def get_health(self, device_id, context):
        return await simulation_runtime_ports.require("governed.domain_client").get_health(device_id, context)

    async def queue_plan(self, plan, context):
        return await simulation_runtime_ports.require("governed.domain_client").queue_plan(plan, context)


class ConnectorOutcomePortProxy:
    async def apply(self, plan, outcome):
        return await simulation_runtime_ports.require("simulation.connector_outcome").apply(plan, outcome)


class KnowledgeMappingPortProxy:
    async def resolve_resource_models(self, items, context):
        return await simulation_runtime_ports.require("governed.domain_client").resolve_resource_models(items, context)


__all__ = [
    "ConnectorOutcomePortProxy", "ConnectorPortProxy", "CraftExecutionPlanPortProxy", "CraftScreenshotPortProxy",
    "GovernedSimulationRuntimeClient", "KnowledgeMappingPortProxy", "SimulationRuntimePorts",
    "configure_simulation_runtime_gateway", "simulation_runtime_ports",
]
