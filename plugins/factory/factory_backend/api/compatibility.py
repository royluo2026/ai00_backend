"""HTTP compatibility transport for the official Factory Provider."""
from __future__ import annotations

from backend.capability_v2.web_compatibility import build_trusted_web_envelope, invoke_trusted_web_compatibility


def build_web_compatibility_envelope(gateway, *, capability_id, payload, current_user, principal, request_id, trace_id, idempotency_key=None, approval_reference=None, major_version=1):
    return build_trusted_web_envelope(
        gateway, capability_id=capability_id, payload=payload, current_user=current_user,
        principal=principal, consumer_id="ai00.web.factory.compatibility",
        request_id=request_id, trace_id=trace_id, idempotency_key=idempotency_key,
        approval_reference=approval_reference, major_version=major_version,
    )


async def invoke_compatibility(gateway, envelope):
    return await invoke_trusted_web_compatibility(gateway, envelope)
