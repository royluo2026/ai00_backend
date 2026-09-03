"""Device Connector adapter used by Simulation orchestration."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError

from ..capabilities.connector_runtime import connector_control_plane, queue_connector_plan


class SimulationConnectorAdapter:
    def __init__(
        self, snapshot_loader: Callable[[str, Any], Mapping[str, Any]] | None = None,
    ) -> None:
        self._snapshot_loader = snapshot_loader

    def get_health(self, device_id: str, context: Any) -> Any:
        return connector_control_plane.get_health(device_id, context)

    def queue_plan(self, plan: Any, context: Any) -> Any:
        return queue_connector_plan(plan, context)

    def get_document_snapshot(self, device_id: str, context: Any) -> Mapping[str, Any]:
        if self._snapshot_loader is None:
            raise CapabilityBusinessError(
                "active_document_snapshot_required",
                "A confirmed VisMockup document snapshot is required",
                retryable=True,
            )
        return self._snapshot_loader(device_id, context)


__all__ = ["SimulationConnectorAdapter"]
