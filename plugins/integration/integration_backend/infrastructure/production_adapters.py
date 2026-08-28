"""Safe production composition when external vault/runtime adapters are not configured."""
from __future__ import annotations

from pathlib import Path
from datetime import UTC, datetime

from backend.capability_v2.catalog import CatalogRelease, CatalogResolver
from backend.capability_v2.catalog_lineage import CatalogLineage
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, TenantIdentity
from backend.capability_v2.domain_client import DomainCapabilityClient
from backend.capability_v2.gateway import get_default_gateway

from ..capabilities.wiring import IntegrationProviderAdapters
from .target_catalog import IntegrationTargetCatalog


_ROOT = Path(__file__).resolve().parents[4]
_CATALOG_PATH = _ROOT / "docs/governance/capability-catalog-release.json"
_LINEAGE_PATH = _ROOT / "docs/governance/capability-catalog-lineage.json"


class _UnavailableProviderRegistry:
    def get(self, *_args, **_kwargs):
        raise KeyError("provider_resolution_unavailable")


class _UnavailableCredentialEnrollment:
    def consume(self, _handle, _actor_gid, _team_gid):
        raise RuntimeError("credential_enrollment_unavailable")


class _UnavailableConnectorRuntime:
    async def test(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")

    async def discover(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")

    async def source_columns(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")

    async def preview(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")


class _LazyDomainCapabilityClient(DomainCapabilityClient):
    def __init__(self):
        pass

    async def invoke(self, invocation, identity, correlation, deadline=None):
        return await DomainCapabilityClient(get_default_gateway()).invoke(
            invocation, identity, correlation, deadline
        )


def build() -> IntegrationProviderAdapters:
    """Publish only the local Catalog path; unavailable external ports fail on use."""
    release = CatalogRelease.model_validate_json(_CATALOG_PATH.read_text(encoding="utf-8"))
    lineage = CatalogLineage.model_validate_json(_LINEAGE_PATH.read_text(encoding="utf-8"))
    store = InMemoryCatalogStore()
    store.publish(release)
    resolver = CatalogResolver(store, _UnavailableProviderRegistry())

    def identity_for(run) -> ConsumerIdentity:
        owner = str(run.get("owner_gid") or "").strip()
        if not owner:
            raise RuntimeError("persisted_worker_principal_missing")
        tenant = str(run.get("team_gid") or f"user:{owner}")
        return ConsumerIdentity(
            actor=ActorIdentity(user_id=owner, authentication_method="persisted-integration-operation", authenticated_at=datetime.now(UTC)),
            tenant=TenantIdentity(tenant_id=tenant, membership="persisted-operation"),
            consumer=ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id="domain.integration.import-worker"),
        )
    return IntegrationProviderAdapters(
        credential_enrollment=_UnavailableCredentialEnrollment(),
        catalog=IntegrationTargetCatalog(
            catalog_resolver=resolver,
            active_release_id=release.release_id,
            release_lineage=lineage,
        ),
        connector_runtime=_UnavailableConnectorRuntime(),
        target_client=_LazyDomainCapabilityClient(),
        worker_identity_factory=identity_for,
    )


__all__ = ["build"]
