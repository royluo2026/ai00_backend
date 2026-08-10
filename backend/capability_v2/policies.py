"""Policy interfaces used by the fixed Gateway pipeline."""
from __future__ import annotations

from typing import Any, Protocol

from backend.capabilities.registry_next import RegisteredCapability

from .contracts import CapabilityDescriptorV2, ConsumerIdentity, InvocationEnvelope


class GatewayPolicyError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class GatewayPolicy(Protocol):
    def authorize(self, descriptor: CapabilityDescriptorV2, envelope: InvocationEnvelope,
                  provider: RegisteredCapability) -> None: ...
    def approve(self, descriptor: CapabilityDescriptorV2, envelope: InvocationEnvelope,
                provider: RegisteredCapability) -> None: ...
    def project(self, descriptor: CapabilityDescriptorV2, identity: ConsumerIdentity,
                data: Any) -> Any: ...


class FailClosedGatewayPolicy:
    """Safe default until the ABAC and persistent approval services are wired."""

    def authorize(self, descriptor, envelope, provider) -> None:
        if provider.spec.permissions:
            raise GatewayPolicyError("authorization_policy_unavailable", "Authorization policy is not configured.")

    def approve(self, descriptor, envelope, provider) -> None:
        if descriptor.confirmation_policy != "none":
            raise GatewayPolicyError("approval_service_unavailable", "Persistent approval service is not configured.")

    def project(self, descriptor, identity, data):
        return data


class LegacyServerGatewayPolicy:
    """Server-side bridge for reviewed V1 providers during the V2 migration."""

    def authorize(self, descriptor, envelope, provider) -> None:
        actor = envelope.identity.actor
        if actor.user_id is None:
            raise GatewayPolicyError("service_authorization_unavailable", "Service grants are not configured.")
        from backend.routers.deps import build_profile
        from backend.services.user_service import get_by_gid

        user = get_by_gid(actor.user_id)
        if not user or not user.get("is_active", True):
            raise GatewayPolicyError("actor_inactive", "Actor is inactive.")
        granted = set(build_profile(user).get("permissions", ()))
        missing = sorted(set(provider.spec.permissions) - granted)
        if missing:
            raise GatewayPolicyError("permission_denied", f"Missing permissions: {', '.join(missing)}")

    def approve(self, descriptor, envelope, provider) -> None:
        if descriptor.confirmation_policy == "none":
            return
        actor_id = envelope.identity.actor.user_id or envelope.identity.actor.service_id or ""
        if not envelope.approval_reference:
            raise GatewayPolicyError("confirmation_required", "Confirmation is required.")
        from backend.capabilities.confirmation_next import confirmation_manager
        if not confirmation_manager.consume(
            envelope.approval_reference,
            envelope.capability_id,
            envelope.major_version,
            actor_id,
            dict(envelope.payload),
        ):
            raise GatewayPolicyError("confirmation_rejected", "Confirmation is invalid or expired.")

    def project(self, descriptor, identity, data):
        return data


__all__ = [
    "FailClosedGatewayPolicy",
    "GatewayPolicy",
    "GatewayPolicyError",
    "LegacyServerGatewayPolicy",
]
