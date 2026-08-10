"""Trusted in-process adapter for the sole Capability V2 Gateway."""
from __future__ import annotations

import asyncio
from typing import Any

from backend.capability_v2.contracts import InvocationEnvelope
from backend.capability_v2.gateway import get_default_gateway


def invoke_capability(envelope: InvocationEnvelope) -> dict[str, Any]:
    """Invoke a server-constructed envelope from synchronous legacy code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        result = asyncio.run(get_default_gateway().invoke(envelope))
        return result.model_dump(mode="json")
    raise RuntimeError("synchronous capability adapter cannot run inside an active event loop")


def invoke_capability_for_user(
    capability_id: str,
    payload: dict[str, Any],
    *,
    user_gid: str,
    source: str,
) -> dict[str, Any]:
    """Retired unsafe adapter: raw user/source claims cannot create trusted identities."""
    raise PermissionError(
        "trusted ConsumerIdentity or Agent delegation is required; raw user_gid/source invocation is disabled"
    )


__all__ = ["invoke_capability", "invoke_capability_for_user"]
