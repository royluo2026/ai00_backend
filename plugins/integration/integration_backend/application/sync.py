from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from backend.capability_v2.contracts import ConsumerIdentity, CorrelationRef
from backend.capability_v2.domain_client import DomainCapabilityClient, DomainInvocation


@dataclass(frozen=True)
class TargetAdapter:
    target_domain: str
    capability_id: str
    major_version: int
    minimum_catalog_release: str


class SyncService:
    def __init__(self, client: DomainCapabilityClient, identity: ConsumerIdentity):
        self._client = client
        self._identity = identity

    async def apply_batch(
        self, *, adapter: TargetAdapter, payload: Mapping[str, Any], idempotency_key: str,
        correlation: CorrelationRef,
    ) -> Any:
        if not adapter.capability_id.startswith(adapter.target_domain + "."):
            raise ValueError("target adapter domain and capability do not match")
        invocation = DomainInvocation(
            capability_id=adapter.capability_id,
            major_version=adapter.major_version,
            payload=dict(payload),
            idempotency_key=idempotency_key,
        )
        return await self._client.invoke(invocation, self._identity, correlation)

