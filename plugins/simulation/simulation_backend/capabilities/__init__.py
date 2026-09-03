"""Official Simulation Capability provider."""
from __future__ import annotations

from typing import Any

from backend.domain_ports.simulation_runtime import simulation_runtime_ports

from .models import specs
from .environment_composition import EnvironmentCompositionProvider, specs as composition_specs
from .capture_runs import CaptureRunProvider, specs as capture_specs
from ..application.capture_worker import ConnectorOutcomeProjection
from .capture_runs import default_provider as default_capture_provider
from .document_snapshots import default_workflow as default_snapshot_workflow
from .document_snapshots import specs as document_snapshot_specs
from .provider import register


def register_capabilities(
    registry: Any, *, composition_provider: EnvironmentCompositionProvider | None = None,
    capture_provider: CaptureRunProvider | None = None,
) -> None:
    selected_capture_provider = capture_provider or default_capture_provider
    simulation_runtime_ports.register(
        "simulation.connector_outcome",
        ConnectorOutcomeProjection(selected_capture_provider.workflow, default_snapshot_workflow),
    )
    for spec, handler in specs():
        register(registry, spec, handler)
    for spec, handler in composition_specs(composition_provider) if composition_provider else composition_specs():
        register(registry, spec, handler)
    for spec, handler in capture_specs(selected_capture_provider):
        register(registry, spec, handler)
    for spec, handler in document_snapshot_specs():
        register(registry, spec, handler)


__all__ = ["register_capabilities"]
