"""Legacy transport adapter; all execution remains behind Capability Gateway."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import InvocationEnvelope


async def invoke_compatibility(
    gateway: Any, envelope: InvocationEnvelope
) -> Any:
    """Forward an already authenticated server-derived envelope to Gateway."""
    return await gateway.invoke(envelope)


__all__ = ["invoke_compatibility"]
