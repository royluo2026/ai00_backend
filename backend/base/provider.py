"""Base-owned registration boundary for native Capability V2 contracts."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel, CapabilityDescriptorV2, DomainErrorContract,
    ExposurePolicy, LifecycleStatus, ResourceSelector, SideEffectLevel,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS


_LIFECYCLE = {
    "plugin.disable", "plugin.enable", "plugin.install", "plugin.revoke",
    "plugin.rollback", "plugin.uninstall", "plugin.upgrade", "plugin.upgrade.finish",
    "base.plugin.installation.request.create", "base.plugin.installation.transition.uninstall",
}
_STORAGE_WRITES = {"plugin.storage.delete", "plugin.storage.put"}
_WRITES = _LIFECYCLE | _STORAGE_WRITES | {"system.job.cancel"}
_ATOMIC_WEB_EFFECTS = {
    "base.file_store.public_config.get": "Reads a secret-filtered file-store configuration projection without mutation.",
    "base.authorization.grant.list": "Reads active authorization grants from the Base grant store without mutation.",
    "base.authorization.grant.create": "Creates or replaces one scoped authorization grant in the Base grant store.",
    "base.authorization.grant.revoke": "Deletes one existing scoped authorization grant from the Base grant store.",
    "base.notification.preference.atomic.get": "Reads the caller's notification preferences without mutation.",
    "base.notification.preference.atomic.update": "Updates the caller's notification preferences in the Base store.",
    "base.identity.directory.feishu.sync": "Reads the Feishu directory and applies team and user changes to the Base store.",
    "base.plugin.installed.list": "Reads the bounded installed-plugin inventory without mutation.",
    "base.plugin.installation.request.create": "Verifies one signed published marketplace release and creates a tenant-bound disabled installation with explicit grants.",
    "base.plugin.installation.transition.uninstall": "Atomically revokes mounts and grants, preserves tenant data, and records a recoverable uninstall transition.",
    "base.identity.user.search": "Reads and projects matching Base directory users without mutation.",
    "base.organization.team.directory.list": "Reads a closed organization-team directory projection without mutation.",
    "base.team.directory.list": "Reads a closed active-team directory projection without mutation.",
    "base.self_annotation.batch.get": "Reads the caller's bounded self-annotation summaries without mutation.",
    "base.self_annotation.record.get": "Reads one caller-owned closed self-annotation projection without mutation.",
    "base.self_annotation.search": "Reads a bounded caller-owned self-annotation collection without mutation.",
    "base.self_annotation.change.apply": "Revision-locks one caller-owned typed self-annotation update with replay and audit evidence.",
    "base.identity.session.profile.get": "Reads the caller's closed browser-visible identity projection without credentials or tokens.",
    "base.identity.admin_user.list": "Reads a closed administrator-visible user directory projection without mutation.",
    "base.identity.role.assign.atomic": "Atomically changes one user's role after administrator authorization.",
    "base.saved_view.search": "Reads only saved views visible to the caller through the Base aggregate service.",
    "base.saved_view.create": "Creates one closed saved-view aggregate with idempotency and audit evidence.",
    "base.saved_view.update": "Revision-locks one saved-view aggregate update with audit evidence.",
    "base.saved_view.copy": "Copies one visible saved view into a new private owner-bound aggregate.",
    "base.saved_view.delete": "Revision-locks a recoverable saved-view tombstone with audit evidence.",
}
_ATOMIC_WEB_STRONG_WRITES = {
    "base.identity.role.assign.atomic", "base.saved_view.create", "base.saved_view.update",
    "base.saved_view.copy", "base.saved_view.delete", "base.self_annotation.change.apply",
    "base.plugin.installation.request.create", "base.plugin.installation.transition.uninstall",
}
_RESOURCE_FIELDS = {
    **{capability_id: ("plugin-installation", "plugin_id") for capability_id in _LIFECYCLE},
    **{capability_id: ("plugin-storage-key", "key") for capability_id in {
        "plugin.storage.delete", "plugin.storage.get", "plugin.storage.put",
    }},
    "system.job.get": ("system-job", "job_gid"),
    "system.job.cancel": ("system-job", "job_gid"),
}
_DOMAIN_ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable) for code, meaning, retryable in (
    ("resource_not_found", "The requested Base resource does not exist or is not visible.", False),
    ("permission_denied", "The caller lacks a required Base Platform permission.", False),
    ("approval_required", "The governed operation requires a valid approval.", False),
    ("authentication_stale", "The caller must authenticate again before this high-risk operation.", False),
    ("idempotency_conflict", "The idempotency key is bound to a different request.", False),
    ("version_conflict", "The resource version differs from the expected version.", False),
    ("provider_unavailable", "A required domain provider is not registered.", True),
    ("plugin_state_conflict", "The plugin installation cannot perform this lifecycle transition.", False),
))
_STRUCTURAL_ERROR_CODES = {
    "base.saved_view.search": {"invalid_input"},
    "base.saved_view.create": {"invalid_input", "idempotency_conflict"},
    "base.saved_view.update": {"invalid_input", "idempotency_conflict", "legacy_config_unsupported", "permission_denied", "resource_not_found", "revision_conflict"},
    "base.saved_view.copy": {"invalid_input", "idempotency_conflict", "legacy_config_unsupported", "resource_not_found"},
    "base.saved_view.delete": {"invalid_input", "idempotency_conflict", "legacy_config_unsupported", "permission_denied", "resource_not_found", "revision_conflict"},
    "base.self_annotation.batch.get": {"invalid_input"},
    "base.self_annotation.record.get": {"invalid_input"},
    "base.self_annotation.search": {"invalid_input"},
    "base.self_annotation.change.apply": {"attachment_not_visible", "idempotency_conflict", "invalid_input", "revision_conflict"},
    "base.identity.session.profile.get": {"identity_not_found", "invalid_input", "tenant_mismatch"},
    "base.plugin.installation.request.create": {"already_installed", "idempotency_conflict", "invalid_input", "release_not_verified"},
    "base.plugin.installation.transition.uninstall": {"idempotency_conflict", "invalid_input", "invalid_transition", "release_not_verified", "resource_not_found", "revision_conflict"},
}


def _domain_errors(capability_id: str) -> tuple[DomainErrorContract, ...]:
    codes = _STRUCTURAL_ERROR_CODES.get(capability_id)
    if codes is None:
        return _DOMAIN_ERRORS
    return tuple(DomainErrorContract(code=code, meaning=f"{capability_id} can return {code}.", retryable=False) for code in sorted(codes))


def _governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={
        "owner": "base",
        "plugin_callable": True,
        "input_schema": INPUT_SCHEMAS[spec.id],
        "output_schema": OUTPUT_SCHEMAS[spec.id],
    })


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    governed = _governed_spec(spec)
    descriptor = descriptor_from_provider_spec(governed)
    capability_id = governed.id
    is_write = capability_id in _WRITES or descriptor.side_effect_level is not SideEffectLevel.READ
    resource = _RESOURCE_FIELDS.get(capability_id)
    updates = {
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A0 if capability_id in _LIFECYCLE else (AutomationLevel.A1 if is_write else AutomationLevel.A2),
        "authorization_policy": "base.v2:system.plugin.manage" if capability_id in _LIFECYCLE else "base.v2:" + (",".join(governed.permissions) or "authenticated"),
        "resource_selectors": (ResourceSelector(resource_type=resource[0], payload_path=resource[1]),) if resource else (),
        "data_classification": "restricted" if capability_id in _LIFECYCLE else "confidential",
        "required_auth_freshness_seconds": 300 if capability_id in _LIFECYCLE else 0,
        "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "operation_policy": "optional" if is_write else "none",
        "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": "external" if is_write else "strong",
        "evidence_policy": "optional",
        "audit_policy": "high_risk" if capability_id in _LIFECYCLE else "standard",
        "domain_errors": _domain_errors(capability_id),
        "domain_errors_complete": True,
    }
    if capability_id in _ATOMIC_WEB_EFFECTS:
        updates["business_effect"] = _ATOMIC_WEB_EFFECTS[capability_id]
        updates["side_effects"] = _ATOMIC_WEB_EFFECTS[capability_id]
        updates["transaction_policy"] = {
            "mode": "external" if capability_id == "base.identity.directory.feishu.sync" else "provider",
            "boundary": "owning_domain",
        }
    if capability_id in _ATOMIC_WEB_STRONG_WRITES:
        updates["consistency_policy"] = "strong"
        updates["transaction_policy"] = {"mode": "single_transaction", "boundary": "owning_domain"}
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    governed = _governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["descriptor_for", "register_capability"]
