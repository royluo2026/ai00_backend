"""Neutral typed-port bindings populated by the resource-owning domains."""
from __future__ import annotations

from threading import RLock
from typing import Any


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


class CraftExecutionPlanPortProxy:
    def get_execution_plan(self, reference, context):
        return simulation_runtime_ports.require("craft.execution_plan").get_execution_plan(reference, context)


class CraftScreenshotPortProxy:
    def attach_screenshot(self, **kwargs):
        return simulation_runtime_ports.require("craft.screenshot").attach_screenshot(**kwargs)


class ConnectorPortProxy:
    def get_document_snapshot(self, device_id, context):
        return simulation_runtime_ports.require("device.connector").get_document_snapshot(device_id, context)

    def get_health(self, device_id, context):
        return simulation_runtime_ports.require("device.connector").get_health(device_id, context)

    def queue_plan(self, plan, context):
        return simulation_runtime_ports.require("device.connector").queue_plan(plan, context)


class KnowledgeMappingPortProxy:
    def resolve_resource_models(self, items, context):
        return simulation_runtime_ports.require("knowledge.resource_model_mapping").resolve_resource_models(items, context)


__all__ = [
    "ConnectorPortProxy", "CraftExecutionPlanPortProxy", "CraftScreenshotPortProxy",
    "KnowledgeMappingPortProxy", "SimulationRuntimePorts", "simulation_runtime_ports",
]
