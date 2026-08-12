"""Official Digital Model Capability provider."""
from __future__ import annotations

from typing import Any

from .models import specs
from .models import resolve_snapshot_reference
from .provider import register
from backend.domain_ports.versioned_resources import versioned_resource_resolvers


def register_capabilities(registry: Any) -> None:
    for spec, handler in specs():
        register(registry, spec, handler)
    versioned_resource_resolvers.register("digital_model.version", resolve_snapshot_reference)


__all__ = ["register_capabilities"]
