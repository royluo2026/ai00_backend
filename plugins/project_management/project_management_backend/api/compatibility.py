"""Legacy transport adapter; all execution remains behind Capability Gateway."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    InvocationEnvelope,
    TenantIdentity,
)


def build_web_compatibility_envelope(
    gateway: Any,
    *,
    capability_id: str,
    payload: dict[str, Any],
    current_user: dict[str, Any],
    principal: Any,
    request_id: str,
    trace_id: str,
    idempotency_key: str | None = None,
    approval_reference: str | None = None,
) -> InvocationEnvelope:
    """Construct trusted identity and tenant fields outside client payloads."""
    return InvocationEnvelope(
        capability_id=capability_id,
        major_version=1,
        catalog_release=gateway.catalog_release,
        payload=payload,
        identity=ConsumerIdentity(
            actor=ActorIdentity(**principal.model_dump()),
            tenant=TenantIdentity(
                tenant_id=str(current_user.get("team_id") or "default"),
                membership="member",
                active_roles=tuple(
                    filter(
                        None,
                        (
                            current_user.get("org_role"),
                            current_user.get("system_role"),
                        ),
                    )
                ),
            ),
            consumer=ConsumerDescriptor(
                type=ConsumerType.WEB,
                consumer_id="ai00.web.compatibility",
            ),
        ),
        idempotency_key=idempotency_key,
        approval_reference=approval_reference,
        request_id=request_id,
        trace_id=trace_id,
    )


async def invoke_compatibility(
    gateway: Any, envelope: InvocationEnvelope
) -> Any:
    """Forward an already authenticated server-derived envelope to Gateway."""
    return await gateway.invoke(envelope)


__all__ = ["build_web_compatibility_envelope", "invoke_compatibility"]
