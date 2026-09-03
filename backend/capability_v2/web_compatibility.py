"""Governed confirmation bridge for authenticated first-party web adapters."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)


def build_trusted_web_envelope(
    gateway: Any, *, capability_id: str, payload: dict[str, Any],
    current_user: dict[str, Any], principal: Any, consumer_id: str,
    request_id: str, trace_id: str, idempotency_key: str | None = None,
    approval_reference: str | None = None, major_version: int = 1,
) -> InvocationEnvelope:
    """Build a server-owned Web invocation with an explicit consumer identity."""
    return InvocationEnvelope(
        capability_id=capability_id,
        major_version=major_version,
        catalog_release=gateway.catalog_release,
        payload=payload,
        identity=ConsumerIdentity(
            actor=ActorIdentity(**principal.model_dump()),
            tenant=TenantIdentity(
                tenant_id=str(current_user.get("team_id") or f"user:{current_user['gid']}"),
                membership="member",
                active_roles=tuple(filter(None, (current_user.get("org_role"), current_user.get("system_role")))),
            ),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id=consumer_id),
        ),
        idempotency_key=idempotency_key,
        approval_reference=approval_reference,
        request_id=request_id,
        trace_id=trace_id,
    )


async def invoke_trusted_web_compatibility(
    gateway: Any,
    envelope: InvocationEnvelope,
) -> Any:
    """Invoke a legacy web envelope and satisfy one missing confirmation.

    Compatibility routes derive identity and payload on the server.  They may
    therefore request the exact Gateway approval after an unapproved write is
    rejected, then retry that same envelope once.  Explicit caller approvals,
    non-Web consumers, and every other Gateway error remain untouched.
    """
    result = await gateway.invoke(envelope)
    if (
        result.ok
        or result.error is None
        or result.error.code != "confirmation_required"
        or envelope.approval_reference is not None
        or envelope.identity.consumer.type is not ConsumerType.WEB
    ):
        return result

    challenge_envelope = envelope.model_copy(
        update={"idempotency_key": envelope.idempotency_key or envelope.request_id}
    )
    issued = await gateway.request_approval(challenge_envelope)
    return await gateway.invoke(
        challenge_envelope.model_copy(update={"approval_reference": issued.token})
    )


__all__ = ["build_trusted_web_envelope", "invoke_trusted_web_compatibility"]
