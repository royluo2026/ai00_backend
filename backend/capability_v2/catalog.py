"""Immutable, content-addressed Capability V2 catalog releases."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Protocol

from pydantic import Field, model_validator

from .business_definition import business_definition_hash
from .contracts import CapabilityDescriptorV2, ExecutionBudget, FrozenModel, LifecycleStatus

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


_MISSING_DERIVED_HASH = object()


def load_catalog_release(document: Mapping[str, Any] | str | bytes | bytearray) -> CatalogRelease:
    """Parse a Catalog document while verifying its generated descriptor hashes."""
    if isinstance(document, (bytes, bytearray)):
        document = document.decode("utf-8")
    if isinstance(document, str):
        document = json.loads(document)
    if not isinstance(document, Mapping):
        raise ValueError("catalog_document_invalid")

    copied = deepcopy(dict(document))
    supplied_hashes: list[object] = []
    descriptors = copied.get("descriptors")
    if isinstance(descriptors, (list, tuple)):
        for descriptor in descriptors:
            supplied_hashes.append(
                descriptor.pop("business_definition_hash", _MISSING_DERIVED_HASH)
                if isinstance(descriptor, dict) else _MISSING_DERIVED_HASH
            )
    release = CatalogRelease.model_validate(copied)
    for descriptor, supplied_hash in zip(release.descriptors, supplied_hashes):
        if supplied_hash is not _MISSING_DERIVED_HASH and supplied_hash != business_definition_hash(descriptor):
            raise ValueError("business_definition_hash_mismatch")
    return release


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


def build_catalog_entry(item: CapabilityDescriptorV2) -> dict[str, Any]:
    """Return the catalog projection, including its business definition."""
    entry = item.model_dump(mode="json")
    entry.update({
        "business_effect": (item.business_effect or "").strip(),
        "business_acceptance_criteria": list(item.business_acceptance_criteria),
        "business_invariants": [rule.model_dump(mode="json") for rule in item.business_invariants],
        "no_business_invariant_reason": item.no_business_invariant_reason,
        "business_definition_hash": business_definition_hash(item),
    })
    return entry


def complete_governance_metadata(
    item: CapabilityDescriptorV2,
    *,
    provider_ref: str | None = None,
    consumer_refs: tuple[Mapping[str, Any] | str, ...] = (),
    no_consumer_reason: str | None = None,
    api_refs: tuple[str, ...] = (),
    test_refs: tuple[Mapping[str, Any], ...] = (),
) -> CapabilityDescriptorV2:
    """Return a deterministic V2.1 projection without changing business schemas."""
    digest = hashlib.sha256(f"{item.id}@{item.major_version}".encode("utf-8")).hexdigest()[:24]
    business_effect = (item.business_effect or "").strip()
    side_effects = item.side_effects
    if not side_effects or side_effects.strip() in {
        "Reads domain state without mutation.",
        "Writes domain state through the owning Provider.",
    }:
        if item.side_effect_level.value == "read":
            side_effects = f"Reads {item.owner_domain} domain state; emits no mutation event or external call."
        else:
            side_effects = f"Writes {item.owner_domain} domain state through its Provider and records a capability audit event."
    updates: dict[str, Any] = {
        "capability_version_gid": item.capability_version_gid or f"cv2_{digest}",
        "business_effect": business_effect,
        "side_effects": side_effects,
        "transaction_policy": item.transaction_policy or {
            "mode": "provider",
            "boundary": "provider",
        },
        "provider_ref": item.provider_ref or provider_ref or f"{item.owner_domain}.provider",
        "consumer_refs": item.consumer_refs or consumer_refs,
        "no_consumer_reason": item.no_consumer_reason or no_consumer_reason or (
            "No verified consumer is registered for this provider capability."
            if not (item.consumer_refs or consumer_refs)
            else None
        ),
        "api_refs": item.api_refs or api_refs or (
            f"gateway:/api/v1/capabilities/{item.id}:invoke",
        ),
        "test_refs": item.test_refs or test_refs,
    }
    if not item.error_schema and item.domain_errors:
        updates["error_schema"] = tuple(
            error.as_error_schema_entry() for error in item.domain_errors
        )
    return item.model_copy(update=updates)


def _descriptor_document(item: CapabilityDescriptorV2) -> dict:
    document = item.model_dump(mode="json")
    # Pydantic re-validation materializes the V2.1 error projection from the
    # legacy domain_errors tuple. Normalize before hashing so the release hash
    # is identical before and after CatalogRelease validation.
    if not document.get("error_schema") and document.get("domain_errors"):
        document["error_schema"] = [
            {
                "error_code": error["code"],
                "message_template": error["meaning"],
                "is_retryable": error.get("retryable", False),
                "is_caller_error": error.get("is_caller_error", False),
            }
            for error in document["domain_errors"]
        ]
    # Preserve hashes of releases created before this additive optional field existed.
    if document.get("agent_output_schema") is None:
        document.pop("agent_output_schema", None)
    if not document.get("domain_errors"):
        document.pop("domain_errors", None)
    if not document.get("domain_errors_complete"):
        document.pop("domain_errors_complete", None)
    if document.get("expected_version_payload_path") is None:
        document.pop("expected_version_payload_path", None)
    # Releases created before projected synchronous-write replay was introduced
    # remain content-addressable under the fail-closed metadata-only default.
    if document.get("replay_data_policy") == "metadata_only":
        document.pop("replay_data_policy", None)
    # Releases produced before execution budgets were added remain verifiable.
    # A non-default budget is still part of the content-addressed document.
    if item.execution_budget == ExecutionBudget():
        document.pop("execution_budget", None)
    return document


def unbounded_collection_paths(
    schema: Mapping[str, object], path: str = "output_schema",
) -> tuple[str, ...]:
    paths: list[str] = []
    if schema.get("type") == "array":
        if "maxItems" not in schema:
            paths.append(path)
        items = schema.get("items")
        if isinstance(items, Mapping):
            paths.extend(unbounded_collection_paths(items, f"{path}[]"))
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            if isinstance(child, Mapping):
                paths.extend(unbounded_collection_paths(child, f"{path}.{name}"))
    definitions = schema.get("$defs")
    if isinstance(definitions, Mapping):
        for name, child in definitions.items():
            if isinstance(child, Mapping):
                paths.extend(unbounded_collection_paths(child, f"{path}.$defs.{name}"))
    for keyword in ("anyOf", "oneOf", "allOf"):
        alternatives = schema.get(keyword)
        if isinstance(alternatives, (list, tuple)):
            for index, child in enumerate(alternatives):
                if isinstance(child, Mapping):
                    paths.extend(unbounded_collection_paths(child, f"{path}.{keyword}[{index}]"))
    return tuple(paths)


def _validate_collection_boundaries(
    descriptors: Iterable[CapabilityDescriptorV2],
    grandfathered_paths: set[tuple[str, int, str]],
) -> None:
    errors: list[str] = []
    for descriptor in descriptors:
        if descriptor.lifecycle_status is not LifecycleStatus.STABLE:
            continue
        if descriptor.execution_budget.collection_policy.value in {"paged", "artifact"}:
            continue
        for path in unbounded_collection_paths(descriptor.output_schema):
            key = (descriptor.id, descriptor.major_version, path)
            if key not in grandfathered_paths:
                errors.append(
                    f"unbounded stable collection: {descriptor.id}@{descriptor.major_version} {path}"
                )
    if errors:
        raise ValueError("; ".join(sorted(errors)))


def build_release(
    descriptors: Iterable[CapabilityDescriptorV2],
    provider_artifacts: Iterable[ProviderArtifact] = (),
    *,
    created_at: datetime | None = None,
    grandfathered_unbounded_paths: set[tuple[str, int, str]] | None = None,
    enforce_collection_boundaries: bool = False,
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
    if enforce_collection_boundaries:
        _validate_collection_boundaries(
            ordered_descriptors, set(grandfathered_unbounded_paths or ()),
        )
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
        if new.execution_budget != old.execution_budget:
            errors.append(
                f"stable capability execution budget changed without major version bump: {label}"
            )
            continue
        frozen_policy_fields = (
            "authorization_policy",
            "resource_selectors",
            "data_classification",
            "required_auth_freshness_seconds",
            "delegation_policy",
            "artifact_policy",
            "operation_policy",
            "concurrency_policy",
            "expected_version_payload_path",
            "idempotency_policy",
            "replay_data_policy",
            "consistency_policy",
            "confirmation_policy",
            "evidence_policy",
            "audit_policy",
            "domain_errors",
            "error_schema",
            "transaction_policy",
            "timeout_seconds",
            "rate_limit_cost",
        )
        for field in frozen_policy_fields:
            if getattr(new, field) != getattr(old, field):
                errors.append(
                    f"stable capability {field} changed without major version bump: {label}"
                )
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
            registered = self._registry.get(capability_id, major_version)
        except KeyError as exc:
            raise CatalogResolutionError("provider_registration_missing") from exc
        self._verify_provider_artifact(release, registered)
        return registered

    def _verify_provider_artifact(
        self,
        release: CatalogRelease,
        registered: "RegisteredCapability",
    ) -> None:
        if not release.provider_artifacts:
            return
        runtime = self._registry.provider_artifact(registered.spec.owner)
        if runtime is None:
            raise CatalogResolutionError("provider_artifact_unbound")
        expected = next(
            (item for item in release.provider_artifacts if item.plugin_id == runtime.plugin_id),
            None,
        )
        if expected is None:
            raise CatalogResolutionError("provider_artifact_not_in_release")
        if (
            expected.module,
            expected.version,
            expected.artifact_hash,
        ) != (
            runtime.module,
            runtime.version,
            runtime.artifact_hash,
        ):
            raise CatalogResolutionError("provider_artifact_mismatch")

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
    "complete_governance_metadata",
    "compatibility_errors",
    "load_catalog_release",
    "unbounded_collection_paths",
]
