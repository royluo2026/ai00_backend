"""Official Simulation Capability provider."""
from __future__ import annotations

from typing import Any

from .models import specs
from .environment_composition import EnvironmentCompositionProvider, specs as composition_specs
from .capture_runs import CaptureRunProvider, specs as capture_specs
from .provider import register


def register_capabilities(
    registry: Any, *, composition_provider: EnvironmentCompositionProvider | None = None,
    capture_provider: CaptureRunProvider | None = None,
) -> None:
    for spec, handler in specs():
        register(registry, spec, handler)
    for spec, handler in composition_specs(composition_provider) if composition_provider else composition_specs():
        register(registry, spec, handler)
    for spec, handler in capture_specs(capture_provider) if capture_provider else capture_specs():
        register(registry, spec, handler)


__all__ = ["register_capabilities"]
