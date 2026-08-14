"""Governed confirmation bridge for authenticated first-party web adapters."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import ConsumerType, InvocationEnvelope


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


__all__ = ["invoke_trusted_web_compatibility"]
