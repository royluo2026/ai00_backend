"""Official Digital Model Capability provider."""
from __future__ import annotations

from typing import Any

from .models import authorize_resource, specs
from .models import resolve_snapshot_reference
from .provider import register
from backend.domain_ports.resource_authorization import resource_authorizers
from backend.domain_ports.versioned_resources import versioned_resource_resolvers


def _authorize_model(resource_id, identity) -> bool:
    return authorize_resource(resource_id, identity, version=False)


def _authorize_model_version(resource_id, identity) -> bool:
    return authorize_resource(resource_id, identity, version=True)


def register_capabilities(registry: Any) -> None:
    resource_authorizers.register("digital-model", _authorize_model)
    resource_authorizers.register("digital-model-version", _authorize_model_version)
    for spec, handler in specs():
        register(registry, spec, handler)
    versioned_resource_resolvers.register("digital_model.version", resolve_snapshot_reference)


__all__ = ["register_capabilities"]
