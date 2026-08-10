"""Base-owned registration boundary for native Capability V2 contracts."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel, CapabilityDescriptorV2, DomainErrorContract,
    ExposurePolicy, LifecycleStatus, ResourceSelector, SideEffectLevel,
)
from backend.capability_v2.v1_adapter import adapt_v1_spec

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS


_LIFECYCLE = {
    "plugin.disable", "plugin.enable", "plugin.install", "plugin.revoke",
    "plugin.rollback", "plugin.uninstall", "plugin.upgrade", "plugin.upgrade.finish",
}
_STORAGE_WRITES = {"plugin.storage.delete", "plugin.storage.put"}
_WRITES = _LIFECYCLE | _STORAGE_WRITES | {"system.job.cancel"}
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


def _governed_spec(spec: Any) -> Any:
    return spec.model_copy(update={
        "owner": "base",
        "plugin_callable": True,
        "input_schema": INPUT_SCHEMAS[spec.id],
        "output_schema": OUTPUT_SCHEMAS[spec.id],
    })


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    governed = _governed_spec(spec)
    descriptor = adapt_v1_spec(governed)
    capability_id = governed.id
    is_write = capability_id in _WRITES or descriptor.side_effect_level is not SideEffectLevel.READ
    resource = _RESOURCE_FIELDS.get(capability_id)
    updates = {
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
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
        "domain_errors": _DOMAIN_ERRORS,
        "domain_errors_complete": True,
    }
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    governed = _governed_spec(spec)
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["descriptor_for", "register_capability"]
