"""Official Local Integration Capability provider."""
from __future__ import annotations

from typing import Any

from .provider import register
from .runtime import specs
from backend.domain_ports.resource_authorization import resource_authorizers
from .. import control_plane


def _authorize_owned_device(device_id, identity) -> bool:
    return bool(identity.actor.user_id) and control_plane.can_use_device(
        device_id, identity.actor.user_id or "", identity.tenant.tenant_id,
    )


def register_capabilities(registry: Any) -> None:
    resource_authorizers.register("device", _authorize_owned_device)
    for spec, handler in specs():
        register(registry, spec, handler)


__all__ = ["register_capabilities"]
