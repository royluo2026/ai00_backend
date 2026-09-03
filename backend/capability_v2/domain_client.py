"""Governed server-side domain invocation through CapabilityGatewayService."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import uuid
from typing import Any, Mapping

from .contracts import (
    CapabilityResultV2,
    ConsumerIdentity,
    ConsumerDescriptor,
    ConsumerType,
    CorrelationRef,
    DelegationContext,
    AutomationLevel,
    InvocationEnvelope,
    SideEffectLevel,
)
from .gateway import CapabilityGatewayService


class DomainInvocationError(ValueError):
    """Raised when an internal invocation violates the Gateway contract."""


@dataclass(frozen=True)
class DomainInvocation:
    capability_id: str
    major_version: int
    payload: Mapping[str, Any]
    idempotency_key: str | None = None
    expected_resource_version: str | None = None
    approval_reference: str | None = None


class DomainCapabilityClient:
    def __init__(self, gateway: CapabilityGatewayService, *, parent_envelope: InvocationEnvelope | None = None) -> None:
        self._gateway = gateway
        self._parent_envelope = parent_envelope

    @property
    def catalog_release(self) -> str:
        return self._gateway.catalog_release

    def catalog(self):
        return self._gateway.catalog(self.catalog_release)

    async def invoke(
        self,
        invocation: DomainInvocation,
        identity: ConsumerIdentity,
        correlation: CorrelationRef,
        deadline: datetime | None = None,
    ) -> CapabilityResultV2:
        if {"tenant_id", "tenant_gid"} & set(invocation.payload):
            raise DomainInvocationError("tenant_payload_forbidden")

        release_id = self._gateway.catalog_release
        descriptor = self._gateway.catalog(release_id).descriptor(
            invocation.capability_id,
            invocation.major_version,
        )
        if descriptor is None:
            raise DomainInvocationError("capability_descriptor_not_found")
        if (
            descriptor.side_effect_level is not SideEffectLevel.READ
            and descriptor.idempotency_policy == "required"
            and not invocation.idempotency_key
        ):
            raise DomainInvocationError("idempotency_key_required")

        envelope = InvocationEnvelope(
            capability_id=invocation.capability_id,
            major_version=invocation.major_version,
            catalog_release=release_id,
            payload=dict(invocation.payload),
            identity=identity,
            idempotency_key=invocation.idempotency_key,
            expected_resource_version=invocation.expected_resource_version,
            approval_reference=invocation.approval_reference,
            request_id=correlation.request_id,
            trace_id=correlation.trace_id or correlation.request_id,
            deadline=deadline,
        )
        return await self._gateway.invoke(envelope)

    def issue_agent_run_identity(
        self, parent: ConsumerIdentity, *, agent_run_id: str, session_gid: str,
        capability_scopes: tuple[str, ...], resource_scopes: tuple[str, ...] = (),
        lifetime_seconds: int = 600,
    ) -> ConsumerIdentity:
        """Create a server-owned Agent delegation bound to one run and session."""
        if parent.consumer.type is not ConsumerType.WEB or not parent.actor.user_id:
            raise DomainInvocationError("agent_delegation_parent_invalid")
        now = datetime.now(UTC)
        return parent.model_copy(update={
            "consumer": ConsumerDescriptor(
                type=ConsumerType.AGENT, consumer_id="agent.xiaorou",
                agent_run_id=agent_run_id,
            ),
            "delegation": DelegationContext(
                delegation_id=f"agent-delegation-{uuid.uuid4().hex}",
                delegated_by=parent.actor.user_id,
                capability_scopes=capability_scopes,
                resource_scopes=tuple(dict.fromkeys((
                    f"agent-session:{session_gid}", *resource_scopes,
                ))),
                data_scopes=("confidential",),
                catalog_release=self.catalog_release,
                maximum_automation_level=AutomationLevel.A2,
                expires_at=now + timedelta(seconds=lifetime_seconds),
            ),
        })

    async def _invoke_from_confirmed_parent(
        self,
        invocation: DomainInvocation,
        identity: ConsumerIdentity,
        correlation: CorrelationRef,
        deadline: datetime | None = None,
    ) -> CapabilityResultV2:
        """Invoke a nested target from the Gateway-confirmed parent envelope.

        The Gateway still authorizes, validates, and issues the exact approval for
        the target envelope.  This method is intentionally separate from
        ``invoke`` so ordinary domain-to-domain calls cannot acquire approvals.
        """
        parent = self._parent_envelope
        if invocation.approval_reference is not None:
            raise DomainInvocationError("caller_approval_reference_forbidden")
        if parent is None or not parent.approval_reference:
            raise DomainInvocationError("confirmed_parent_required")
        parent_descriptor = self.catalog().descriptor(parent.capability_id, parent.major_version)
        if parent_descriptor is None or parent_descriptor.confirmation_policy == "none":
            raise DomainInvocationError("confirmed_parent_required")
        result = await self.invoke(invocation, identity, correlation, deadline)
        if result.ok or result.error is None or result.error.code != "confirmation_required":
            return result

        approved = DomainInvocation(
            capability_id=invocation.capability_id,
            major_version=invocation.major_version,
            payload=invocation.payload,
            idempotency_key=invocation.idempotency_key or correlation.request_id,
            expected_resource_version=invocation.expected_resource_version,
        )
        release_id = self._gateway.catalog_release
        envelope = InvocationEnvelope(
            capability_id=approved.capability_id,
            major_version=approved.major_version,
            catalog_release=release_id,
            payload=dict(approved.payload),
            identity=identity,
            idempotency_key=approved.idempotency_key,
            expected_resource_version=approved.expected_resource_version,
            request_id=correlation.request_id,
            trace_id=correlation.trace_id or correlation.request_id,
            deadline=deadline,
        )
        issued = await self._gateway.request_approval(envelope)
        return await self._gateway.invoke(
            envelope.model_copy(update={"approval_reference": issued.token})
        )


__all__ = [
    "DomainCapabilityClient",
    "DomainInvocation",
    "DomainInvocationError",
]
