"""Governed server-side domain invocation through CapabilityGatewayService."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .contracts import (
    CapabilityResultV2,
    ConsumerIdentity,
    CorrelationRef,
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
    def __init__(self, gateway: CapabilityGatewayService) -> None:
        self._gateway = gateway

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


__all__ = [
    "DomainCapabilityClient",
    "DomainInvocation",
    "DomainInvocationError",
]
