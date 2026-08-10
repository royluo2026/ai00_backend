"""Policy interfaces used by the fixed Gateway pipeline."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from backend.capabilities.registry_next import RegisteredCapability

from .authorization import AuthorizationDecision, AuthorizationGrants, CapabilityAuthorizer
from .contracts import CapabilityDescriptorV2, ConsumerIdentity, InvocationEnvelope
from .reliability import ApprovalService, ReliabilityError


class GatewayPolicyError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class GatewayPolicy(Protocol):
    def authorize(self, descriptor: CapabilityDescriptorV2, envelope: InvocationEnvelope,
                  provider: RegisteredCapability) -> AuthorizationDecision | None: ...
    def approve(self, descriptor: CapabilityDescriptorV2, envelope: InvocationEnvelope,
                provider: RegisteredCapability, authorization: AuthorizationDecision | None) -> None: ...
    def project(self, descriptor: CapabilityDescriptorV2, identity: ConsumerIdentity,
                data: Any) -> Any: ...
    def issue_approval(self, descriptor: CapabilityDescriptorV2, envelope: InvocationEnvelope,
                       provider: RegisteredCapability,
                       authorization: AuthorizationDecision): ...


class FailClosedGatewayPolicy:
    """Safe default until the ABAC and persistent approval services are wired."""

    def authorize(self, descriptor, envelope, provider) -> AuthorizationDecision:
        if provider.spec.permissions:
            raise GatewayPolicyError("authorization_policy_unavailable", "Authorization policy is not configured.")

    def approve(self, descriptor, envelope, provider, authorization=None) -> None:
        if descriptor.confirmation_policy != "none":
            raise GatewayPolicyError("approval_service_unavailable", "Persistent approval service is not configured.")

    def project(self, descriptor, identity, data):
        return data

    def issue_approval(self, descriptor, envelope, provider, authorization):
        raise GatewayPolicyError("approval_service_unavailable", "Approval service is not configured.")


class LegacyServerGatewayPolicy:
    """Server-side bridge for reviewed V1 providers during the V2 migration."""

    def __init__(
        self,
        user_loader: Callable[[str], dict | None],
        grants_resolver: Callable[[ConsumerIdentity, dict], AuthorizationGrants],
        approval_service: ApprovalService | None = None,
    ) -> None:
        self._user_loader = user_loader
        self._grants_resolver = grants_resolver
        self._approvals = approval_service

    def authorize(self, descriptor, envelope, provider) -> None:
        actor = envelope.identity.actor
        if actor.user_id is None:
            raise GatewayPolicyError("service_authorization_unavailable", "Service grants are not configured.")
        user = self._user_loader(actor.user_id)
        if not user or not user.get("is_active", True):
            raise GatewayPolicyError("actor_inactive", "Actor is inactive.")
        grants = self._grants_resolver(envelope.identity, user)
        decision = CapabilityAuthorizer(lambda _identity: grants).authorize(
            descriptor, envelope, required_permissions=tuple(provider.spec.permissions)
        )
        if not decision.allowed:
            raise GatewayPolicyError(decision.code, "Capability authorization was denied.")
        return decision

    def approve(self, descriptor, envelope, provider, authorization=None) -> None:
        if descriptor.confirmation_policy == "none":
            return
        if self._approvals is None:
            raise GatewayPolicyError("approval_service_unavailable", "Approval service is unavailable.")
        if not envelope.approval_reference or authorization is None:
            raise GatewayPolicyError("confirmation_required", "Confirmation is required.")
        if not self._approvals.consume(
            envelope.approval_reference,
            descriptor,
            envelope,
            resource_refs=authorization.resource_refs,
            policy_version=authorization.policy_version,
        ):
            raise GatewayPolicyError("confirmation_rejected", "Confirmation is invalid or expired.")

    def issue_approval(self, descriptor, envelope, provider, authorization):
        if self._approvals is None:
            raise GatewayPolicyError("approval_service_unavailable", "Approval service is unavailable.")
        try:
            return self._approvals.issue(
                descriptor, envelope, resource_refs=authorization.resource_refs,
                policy_version=authorization.policy_version,
            )
        except ReliabilityError as exc:
            raise GatewayPolicyError(str(exc), "Approval policy denied the request.") from exc

    def project(self, descriptor, identity, data):
        return data


__all__ = [
    "FailClosedGatewayPolicy",
    "GatewayPolicy",
    "GatewayPolicyError",
    "LegacyServerGatewayPolicy",
]
