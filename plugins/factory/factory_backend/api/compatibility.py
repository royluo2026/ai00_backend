"""HTTP compatibility transport for the official Factory Provider."""
from __future__ import annotations

from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, InvocationEnvelope, TenantIdentity
from backend.capability_v2.web_compatibility import invoke_trusted_web_compatibility


def build_web_compatibility_envelope(gateway, *, capability_id, payload, current_user, principal, request_id, trace_id, idempotency_key=None, approval_reference=None):
    return InvocationEnvelope(
        capability_id=capability_id,
        major_version=1,
        catalog_release=gateway.catalog_release,
        payload=payload,
        identity=ConsumerIdentity(
            actor=ActorIdentity(**principal.model_dump()),
            tenant=TenantIdentity(
                tenant_id=str(current_user.get("team_id") or f"user:{current_user['gid']}"),
                membership="member",
                active_roles=tuple(filter(None, (current_user.get("org_role"), current_user.get("system_role")))),
            ),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.factory.compatibility"),
        ),
        idempotency_key=idempotency_key,
        approval_reference=approval_reference,
        request_id=request_id,
        trace_id=trace_id,
    )


async def invoke_compatibility(gateway, envelope):
    return await invoke_trusted_web_compatibility(gateway, envelope)
