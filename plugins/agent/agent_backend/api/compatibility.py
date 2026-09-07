"""First-party Agent HTTP adapters that always execute through Gateway."""
from __future__ import annotations

from typing import Any
import uuid

from fastapi import HTTPException

from backend.capability_v2.contracts import InvocationEnvelope
from backend.capability_v2.identity import AuthenticatedPrincipal, authenticated_user_identity
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.web_compatibility import invoke_trusted_web_compatibility


async def invoke_agent_capability(
    capability_id: str,
    payload: dict[str, Any],
    current_user: dict[str, Any],
    *, principal: AuthenticatedPrincipal,
) -> Any:
    actor_gid = str(current_user.get("gid") or "")
    if not actor_gid:
        raise HTTPException(401, "用户身份缺失")
    request_id = f"agent_web_{uuid.uuid4().hex}"
    gateway = get_default_gateway()
    envelope = InvocationEnvelope(
        capability_id=capability_id,
        major_version=1,
        catalog_release=gateway.catalog_release,
        payload=payload,
        identity=authenticated_user_identity(current_user, principal,
            legacy_consumer_id="ai00.web.agent-compatibility", legacy_tenant_fallback="default"),
        idempotency_key=request_id if not capability_id.endswith(".read") else None,
        request_id=request_id,
        trace_id=request_id,
    )
    result = await invoke_trusted_web_compatibility(gateway, envelope)
    if not result.ok:
        detail = result.error.model_dump(mode="json") if result.error else {"code": "capability_failed"}
        raise HTTPException(400, detail=detail)
    return result.data


__all__ = ["invoke_agent_capability"]
