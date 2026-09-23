"""Detached, read-only local Provider binding. Never creates governance approvals."""
from __future__ import annotations

from dataclasses import dataclass

from backend.capability_v2.business_definition import business_definition_hash, substantive_business_definition_errors
from backend.capability_v2.catalog import CatalogRelease
from backend.capability_v2.contracts import CapabilityDescriptorV2
from .manifest import LocalProviderDeclaration, PluginManifestV21


class ProviderBindingError(ValueError):
    pass


@dataclass(frozen=True)
class ApprovedLocalProvider:
    plugin_id: str
    plugin_version: str
    artifact_sha256: str
    declaration: LocalProviderDeclaration
    descriptor: CapabilityDescriptorV2
    catalog_release: str
    snapshot_gid: int
    governance_version_gid: int
    business_definition_hash: str


def resolve_provider_bindings(manifest: PluginManifestV21, release: CatalogRelease, store) -> tuple[ApprovedLocalProvider, ...]:
    """Resolve only against a persisted current snapshot and its exact decisions.

    The caller separately verifies package signatures/installation state. The ZIP
    cannot contain the snapshot id: the snapshot binds the final ZIP digest.
    """
    if not getattr(store, "persistent", False):
        raise ProviderBindingError("provider_governance_not_persistent")
    snapshot = store.latest_snapshot()
    if snapshot is None:
        raise ProviderBindingError("provider_snapshot_missing")
    document = snapshot.document
    if document.scan_status != "completed" or document.product_release_id != release.release_id or document.catalog_hash != release.catalog_hash:
        raise ProviderBindingError("provider_snapshot_mismatch")
    # Preserve the existing Release Gate's severity boundary; AI notes do not
    # become deterministic blockers merely because this adapter reads them.
    from backend.capability_governance_test.release_gate import _blocking_codes
    findings=tuple(item for item in store.get_findings(snapshot.snapshot_gid)
        if item.get("source_type") not in {"ai","advisory"})
    if _blocking_codes((*document.scan_findings,*findings)):
        raise ProviderBindingError("provider_governance_findings_unresolved")
    artifact = next((item for item in release.provider_artifacts if item.plugin_id == manifest.plugin_id), None)
    if artifact is None or artifact.version != manifest.version or artifact.artifact_hash != "sha256:" + manifest.artifact.sha256 or artifact.module != "local.javascript":
        raise ProviderBindingError("provider_artifact_mismatch")
    bindings = []
    for declaration in manifest.provides:
        descriptor = release.descriptor(declaration.id, declaration.major)
        if descriptor is None:
            raise ProviderBindingError("provider_descriptor_missing")
        expected_ref = f"{manifest.plugin_id}/{declaration.module}#{declaration.export}"
        if (descriptor.owner_domain != declaration.owner_domain or descriptor.provider_ref != expected_ref
                or descriptor.execution_mode.value != "local" or not descriptor.exposure.plugin
                or descriptor.exposure_policy_source != "provider_explicit"
                or descriptor.lifecycle_status.value != "stable" or not descriptor.capability_version_gid):
            raise ProviderBindingError("provider_descriptor_binding_mismatch")
        if substantive_business_definition_errors(descriptor):
            raise ProviderBindingError("provider_business_definition_incomplete")
        if descriptor.authorization_policy != "authenticated" or descriptor.confirmation_policy == "dual":
            raise ProviderBindingError("provider_authorization_policy_unsupported")
        if declaration.result == "json" and descriptor.side_effect_level.value != "read":
            raise ProviderBindingError("provider_json_must_be_read_only")
        if declaration.result == "artifact" and (descriptor.side_effect_level.value != "write" or descriptor.artifact_policy != "output" or descriptor.idempotency_policy != "required" or descriptor.consistency_policy != "external" or descriptor.replay_data_policy != "projected"):
            raise ProviderBindingError("provider_artifact_policy_invalid")
        scanned = next((item for item in document.capabilities if (item.capability_id, item.major_version) == (declaration.id, declaration.major)), None)
        entry = next((item for item in snapshot.entries if (item.capability_id, item.major_version) == (declaration.id, declaration.major)), None)
        definition_hash = business_definition_hash(descriptor)
        if (scanned is None or entry is None or scanned.owner_domain != descriptor.owner_domain
                or entry.owner_domain != descriptor.owner_domain or entry.descriptor_hash != scanned.descriptor_hash
                or scanned.provider_hash != artifact.artifact_hash
                or scanned.descriptor.get("capability_version_gid") != descriptor.capability_version_gid
                or scanned.descriptor.get("business_definition_hash") != definition_hash):
            raise ProviderBindingError("provider_snapshot_binding_mismatch")
        # Compare all descriptor fields, not only business definition projection.
        raw = dict(scanned.descriptor)
        raw.pop("business_definition_hash", None)
        if CapabilityDescriptorV2.model_validate(raw) != descriptor:
            raise ProviderBindingError("provider_descriptor_revision_mismatch")
        review = store.current_business_review(entry.capability_version_gid, definition_hash)
        if (review is None or review.decision != "approved" or review.reviewer_role != "super_admin"
                or review.definition_hash != definition_hash or review.capability_version_gid != entry.capability_version_gid
                or review.evidence_snapshot_gid != snapshot.snapshot_gid):
            raise ProviderBindingError("provider_approval_missing")
        bindings.append(ApprovedLocalProvider(
            manifest.plugin_id, manifest.version, manifest.artifact.sha256, declaration,
            descriptor, release.release_id, snapshot.snapshot_gid, entry.capability_version_gid, definition_hash,
        ))
    return tuple(bindings)
