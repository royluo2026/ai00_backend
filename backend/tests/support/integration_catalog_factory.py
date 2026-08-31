"""Deterministic no-I/O Integration wiring for Catalog and contract acceptance."""
from __future__ import annotations

from integration_backend.capabilities.wiring import IntegrationProviderAdapters


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


def build() -> IntegrationProviderAdapters:
    """Return validated adapters without network, secrets, or external state."""
    return IntegrationProviderAdapters(
        credential_enrollment=_UnavailableCredentialEnrollment(),
        catalog=_EmptyCatalog(),
        connector_runtime=_UnavailableRuntime(),
    )


__all__ = ["build"]
