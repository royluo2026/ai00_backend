"""Immutable, content-addressed Capability V2 catalog releases."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Iterable, Mapping, Protocol

from pydantic import Field, model_validator

from .contracts import CapabilityDescriptorV2, FrozenModel, LifecycleStatus

if TYPE_CHECKING:
    from backend.capabilities.registry_next import CapabilityRegistry, RegisteredCapability


class CatalogResolutionError(LookupError):
    """A requested immutable release or exact capability key cannot be resolved."""


class ProviderArtifact(FrozenModel):
    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    module: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{2,255}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
    artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class CatalogRelease(FrozenModel):
    release_id: str = Field(pattern=r"^rel_[0-9a-f]{32}$")
    catalog_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    descriptors: tuple[CapabilityDescriptorV2, ...]
    provider_artifacts: tuple[ProviderArtifact, ...] = ()
    created_at: datetime

    @model_validator(mode="after")
    def release_contract(self) -> "CatalogRelease":
        descriptor_keys = [(item.id, item.major_version) for item in self.descriptors]
        if len(descriptor_keys) != len(set(descriptor_keys)):
            raise ValueError("duplicate descriptor in catalog release")
        provider_ids = [item.plugin_id for item in self.provider_artifacts]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("duplicate provider in catalog release")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("catalog release created_at must be timezone-aware")
        digest = hashlib.sha256(
            canonical_catalog_bytes(self.descriptors, self.provider_artifacts)
        ).hexdigest()
        if self.catalog_hash != f"sha256:{digest}":
            raise ValueError("catalog_hash_mismatch")
        if self.release_id != f"rel_{digest[:32]}":
            raise ValueError("release_id_mismatch")
        return self

    def descriptor(self, capability_id: str, major_version: int) -> CapabilityDescriptorV2 | None:
        return next(
            (item for item in self.descriptors if item.id == capability_id and item.major_version == major_version),
            None,
        )


def canonical_catalog_bytes(
    descriptors: Iterable[CapabilityDescriptorV2],
    provider_artifacts: Iterable[ProviderArtifact] = (),
) -> bytes:
    descriptor_documents = sorted(
        (_descriptor_document(item) for item in descriptors),
        key=lambda item: (item["id"], item["major_version"]),
    )
    provider_documents = sorted(
        (item.model_dump(mode="json") for item in provider_artifacts),
        key=lambda item: (item["plugin_id"], item["module"], item["version"], item["artifact_hash"]),
    )
    return json.dumps(
        {"descriptors": descriptor_documents, "provider_artifacts": provider_documents},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _descriptor_document(item: CapabilityDescriptorV2) -> dict:
    document = item.model_dump(mode="json")
    # Preserve hashes of releases created before this additive optional field existed.
    if document.get("agent_output_schema") is None:
        document.pop("agent_output_schema", None)
    return document


def build_release(
    descriptors: Iterable[CapabilityDescriptorV2],
    provider_artifacts: Iterable[ProviderArtifact] = (),
    *,
    created_at: datetime | None = None,
) -> CatalogRelease:
    ordered_descriptors = tuple(sorted(descriptors, key=lambda item: (item.id, item.major_version)))
    ordered_providers = tuple(sorted(
        provider_artifacts,
        key=lambda item: (item.plugin_id, item.module, item.version, item.artifact_hash),
    ))
    descriptor_keys = [(item.id, item.major_version) for item in ordered_descriptors]
    if len(descriptor_keys) != len(set(descriptor_keys)):
        raise ValueError("duplicate descriptor in catalog release")
    provider_ids = [item.plugin_id for item in ordered_providers]
    if len(provider_ids) != len(set(provider_ids)):
        raise ValueError("duplicate provider in catalog release")
    digest = hashlib.sha256(canonical_catalog_bytes(ordered_descriptors, ordered_providers)).hexdigest()
    return CatalogRelease(
        release_id=f"rel_{digest[:32]}",
        catalog_hash=f"sha256:{digest}",
        descriptors=ordered_descriptors,
        provider_artifacts=ordered_providers,
        created_at=created_at or datetime.now(UTC),
    )


def compatibility_errors(previous: CatalogRelease, candidate: CatalogRelease) -> list[str]:
    """Report breaking changes to stable keys within one release-upgrade path."""
    candidate_by_key = {(item.id, item.major_version): item for item in candidate.descriptors}
    errors: list[str] = []
    for old in previous.descriptors:
        if old.lifecycle_status is not LifecycleStatus.STABLE:
            continue
        key = (old.id, old.major_version)
        new = candidate_by_key.get(key)
        label = f"{old.id}@{old.major_version}"
        if new is None:
            errors.append(f"stable capability removed: {label}")
            continue
        if new.schema_hash != old.schema_hash:
            errors.append(f"stable capability schema changed without major version bump: {label}")
            continue
        if new.agent_output_schema != old.agent_output_schema:
            errors.append(
                f"stable capability agent projection changed without major version bump: {label}"
            )
            continue
        if new.owner_domain != old.owner_domain:
            errors.append(f"stable capability owner changed without major version bump: {label}")
        if (new.side_effect_level, new.execution_mode) != (old.side_effect_level, old.execution_mode):
            errors.append(f"stable capability execution semantics changed without major version bump: {label}")
        if new.lifecycle_status not in {LifecycleStatus.STABLE, LifecycleStatus.DEPRECATED}:
            errors.append(f"stable capability lifecycle regressed: {label}")
        old_exposure = old.exposure.model_dump()
        new_exposure = new.exposure.model_dump()
        removed_consumers = sorted(name for name, allowed in old_exposure.items() if allowed and not new_exposure[name])
        if removed_consumers:
            errors.append(f"stable capability exposure removed for {','.join(removed_consumers)}: {label}")
    return sorted(errors)


class CatalogStore(Protocol):
    def get(self, release_id: str) -> CatalogRelease | None: ...


class CatalogResolver:
    def __init__(self, store: CatalogStore, registry: "CapabilityRegistry") -> None:
        self._store = store
        self._registry = registry

    def resolve(
        self,
        release_id: str,
        capability_id: str,
        major_version: int | None,
    ) -> "RegisteredCapability":
        if major_version is None:
            raise CatalogResolutionError("major_version_required")
        release = self._store.get(release_id)
        if release is None:
            raise CatalogResolutionError("catalog_release_not_found")
        if release.descriptor(capability_id, major_version) is None:
            raise CatalogResolutionError("capability_not_in_release")
        try:
            return self._registry.get(capability_id, major_version)
        except KeyError as exc:
            raise CatalogResolutionError("provider_registration_missing") from exc

    def descriptor(self, release_id: str, capability_id: str,
                   major_version: int | None) -> CapabilityDescriptorV2:
        if major_version is None:
            raise CatalogResolutionError("major_version_required")
        release = self._store.get(release_id)
        if release is None:
            raise CatalogResolutionError("catalog_release_not_found")
        descriptor = release.descriptor(capability_id, major_version)
        if descriptor is None:
            raise CatalogResolutionError("capability_not_in_release")
        return descriptor

    def catalog(self, release_id: str) -> CatalogRelease:
        release = self._store.get(release_id)
        if release is None:
            raise CatalogResolutionError("catalog_release_not_found")
        return release


__all__ = [
    "CatalogRelease",
    "CatalogResolutionError",
    "CatalogResolver",
    "ProviderArtifact",
    "build_release",
    "canonical_catalog_bytes",
    "compatibility_errors",
]
