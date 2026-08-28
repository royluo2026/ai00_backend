"""Safe production composition when external vault/runtime adapters are not configured."""
from __future__ import annotations

from pathlib import Path

from backend.capability_v2.catalog import CatalogRelease, CatalogResolver
from backend.capability_v2.catalog_lineage import CatalogLineage
from backend.capability_v2.catalog_store import InMemoryCatalogStore

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


def build() -> IntegrationProviderAdapters:
    """Publish only the local Catalog path; unavailable external ports fail on use."""
    release = CatalogRelease.model_validate_json(_CATALOG_PATH.read_text(encoding="utf-8"))
    lineage = CatalogLineage.model_validate_json(_LINEAGE_PATH.read_text(encoding="utf-8"))
    store = InMemoryCatalogStore()
    store.publish(release)
    resolver = CatalogResolver(store, _UnavailableProviderRegistry())
    return IntegrationProviderAdapters(
        credential_enrollment=_UnavailableCredentialEnrollment(),
        catalog=IntegrationTargetCatalog(
            catalog_resolver=resolver,
            active_release_id=release.release_id,
            release_lineage=lineage,
        ),
        connector_runtime=_UnavailableConnectorRuntime(),
    )


__all__ = ["build"]
