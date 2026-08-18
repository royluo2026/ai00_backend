"""Craft-owned registration boundary for native Capability V2 contracts."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    DomainErrorContract,
    ExposurePolicy,
    LifecycleStatus,
    ResourceSelector,
    SideEffectLevel,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec

from .contracts import input_schema_for, output_schema_for


_RESOURCE_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "craft.bop.version.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.execution_structure.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.execution_structure.preview": (("craft-bop-version", "version_gid"),),
    "craft.bop.linked_parts.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.work_package.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.structure.outline.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.entry.detail.get": (("craft-bop-version", "version_gid"),),
    "craft.bop.version.compare": (
        ("craft-bop-version", "from_version_gid"),
        ("craft-bop-version", "to_version_gid"),
    ),
    "craft.pbom.part.search": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.get": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.submit": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.publish": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.archive": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.version.compare": (("craft-pbom-version", "from_version_gid"), ("craft-pbom-version", "to_version_gid")),
    "craft.pbom.draft.change.preview": (("craft-pbom-version", "version_gid"),),
    "craft.pbom.draft.change.apply": (("craft-pbom-version", "version_gid"),),
    "craft.gbop.item.usage.get": (("craft-gbop-item", "item_gid"),),
    "craft.gbop.item.knowledge.list": (("craft-gbop-item", "item_gid"),),
    "craft.bop.draft.change.preview": (("craft-bop-version", "version_gid"),),
    "craft.bop.draft.change.apply": (("craft-bop-preview", "preview_gid"),),
    "craft.bop.version.archive": (("craft-bop-version", "version_gid"),),
}

_EXPECTED_REVISION = {
    "craft.bop.draft.change.preview",
    "craft.bop.execution_structure.preview",
    "craft.bop.version.archive",
}

_DOMAIN_ERRORS = tuple(
    DomainErrorContract(code=code, meaning=meaning)
    for code, meaning in (
        ("bop_version_not_found", "The scoped BOP version does not exist."),
        ("bop_revision_unavailable", "The BOP has no authoritative revision."),
        ("revision_conflict", "The current BOP revision differs from the expected revision."),
        ("bop_entry_not_found", "A referenced BOP entry does not exist."),
        ("bop_link_not_found", "A referenced BOP link does not exist."),
        ("bop_project_unassigned", "The BOP is not assigned to a project."),
        ("version_not_published", "An official execution structure requires a published BOP."),
        ("preview_not_found", "The requested BOP change preview does not exist."),
        ("preview_expired", "The requested BOP change preview has expired."),
        ("preview_already_applied", "The requested BOP change preview was already committed."),
        ("idempotency_conflict", "The idempotency key is already bound to another Craft payload."),
        ("source_not_found", "The requested version creation source does not exist."),
        ("archive_forbidden", "The BOP lifecycle forbids archiving this version."),
        ("pbom_snapshot_not_found", "The scoped PBOM snapshot does not exist."),
        ("active_gbop_not_found", "No active GBOP release exists."),
        ("multiple_active_gbop_releases", "More than one active GBOP release exists."),
        ("active_gbop_item_not_found", "The GBOP item is not in the active release."),
        ("provider_unavailable", "The Craft application provider is unavailable."),
        ("invalid_cursor", "The pagination cursor is invalid."),
        ("invalid_page_size", "The requested page size is outside the capability limit."),
        ("invalid_scope_kind", "The requested BOP scope kind is invalid."),
        ("scope_not_found", "The requested BOP scope does not exist in the version."),
        ("entry_not_found", "The requested BOP entry does not exist in the version."),
        ("entry_detail_too_large", "The BOP entry has too many links for bounded detail output."),
    )
)


def _governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={
        "plugin_callable": True,
        "input_schema": input_schema_for(spec.id, spec.version),
        "output_schema": output_schema_for(spec.id, spec.version),
    })


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    """Create the frozen native descriptor reviewed and released by Craft."""
    governed = _governed_spec(spec)
    descriptor = descriptor_from_provider_spec(governed)
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    selectors = tuple(
        ResourceSelector(resource_type=resource_type, payload_path=payload_path)
        for resource_type, payload_path in _RESOURCE_FIELDS.get(spec.id, ())
    )
    updates = {
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "craft.v2:" + (",".join(governed.permissions) or "authenticated"),
        "resource_selectors": selectors,
        "data_classification": "confidential",
        "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "operation_policy": "optional" if is_write else "none",
        "concurrency_policy": "expected_version" if spec.id in _EXPECTED_REVISION else "none",
        "expected_version_payload_path": "expected_revision" if spec.id in _EXPECTED_REVISION else None,
        "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": "external" if is_write else "strong",
        "evidence_policy": "optional",
        "domain_errors": _DOMAIN_ERRORS,
        "domain_errors_complete": True,
    }
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    governed = _governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


class NativeContractRegistry:
    """Intercept legacy module registration at the Craft provider boundary."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def register(self, spec: Any, handler: Any) -> None:
        register_capability(self._registry, spec, handler)


__all__ = ["NativeContractRegistry", "descriptor_for", "register_capability"]
