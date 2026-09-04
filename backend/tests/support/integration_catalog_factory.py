"""Deterministic no-I/O Integration wiring for Catalog and contract acceptance."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from integration_backend.capabilities.wiring import IntegrationProviderAdapters
from backend.capability_v2.domain_client import DomainCapabilityClient


class _UnavailableCredentialEnrollment:
    def consume(self, *_args, **_kwargs):
        raise RuntimeError("credential_enrollment_unavailable")


class _EmptyCatalog:
    def project_mapping_targets_for_ontology_objects(
        self, _ontology_object_gids, *, actor_gid, team_gid,
    ):
        return []

    def resolve_mapping_target(self, _binding_id, *, actor_gid, team_gid):
        raise LookupError("target_binding_unavailable")

    def require_stable(self, *_args, **_kwargs):
        return None

    def validate_mapping_target(self, candidate):
        return dict(candidate)


class _UnavailableRuntime:
    async def test(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")

    async def discover(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")

    async def source_columns(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")

    async def preview(self, *_args, **_kwargs):
        raise RuntimeError("connector_runtime_unavailable")


class _StubGateway:
    """Minimal gateway stub for local DomainCapabilityClient."""

    @property
    def catalog_release(self) -> str:
        return "local-runtime-stub"

    def catalog(self, _release_id):
        return _EmptyCatalog()


def _stub_worker_identity_factory(payload: Mapping[str, Any]):
    from backend.capability_v2.contracts import (
        ActorIdentity,
        ConsumerDescriptor,
        ConsumerIdentity,
        ConsumerType,
        TenantIdentity,
    )
    now = datetime.now(timezone.utc)
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id="local-runtime-worker",
            authentication_method="local-runtime",
            authenticated_at=now,
        ),
        tenant=TenantIdentity(tenant_id="local-runtime", membership="member"),
        consumer=ConsumerDescriptor(
            type=ConsumerType.WORKER,
            consumer_id="integration.import-worker",
        ),
    )


def build() -> IntegrationProviderAdapters:
    """Return validated adapters without network, secrets, or external state."""
    return IntegrationProviderAdapters(
        credential_enrollment=_UnavailableCredentialEnrollment(),
        catalog=_EmptyCatalog(),
        connector_runtime=_UnavailableRuntime(),
    )


def build_runtime() -> IntegrationProviderAdapters:
    """Return adapters wired for local runtime startup (stub DomainCapabilityClient)."""
    return IntegrationProviderAdapters(
        credential_enrollment=_UnavailableCredentialEnrollment(),
        catalog=_EmptyCatalog(),
        connector_runtime=_UnavailableRuntime(),
        target_client=DomainCapabilityClient(_StubGateway()),
        worker_identity_factory=_stub_worker_identity_factory,
    )


__all__ = ["build", "build_runtime"]
