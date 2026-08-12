"""Native stable descriptors for the reviewed Project Management surface."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    DomainErrorContract,
    ExposurePolicy,
    LifecycleStatus,
    SideEffectLevel,
)
from backend.capability_v2.v1_adapter import adapt_v1_spec


DOMAIN_ERRORS = tuple(
    DomainErrorContract(code=code, meaning=meaning, retryable=retryable)
    for code, meaning, retryable in (
        ("resource_not_found", "The requested project resource is unavailable.", False),
        ("permission_denied", "The caller cannot access the project resource.", False),
        ("approval_required", "The project change requires Base approval.", False),
        ("version_conflict", "The project resource changed concurrently.", False),
        ("provider_unavailable", "The Project Management provider is unavailable.", True),
    )
)


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    descriptor = adapt_v1_spec(spec)
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    return CapabilityDescriptorV2.model_validate(
        {
            **descriptor.model_dump(),
            "lifecycle_status": LifecycleStatus.STABLE,
            "exposure": ExposurePolicy(
                web=True, api=True, plugin=True, agent=True, mcp=True
            ),
            "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
            "authorization_policy": "project_management.v2:"
            + (",".join(spec.permissions) or "authenticated"),
            "data_classification": "confidential",
            "delegation_policy": "scoped",
            "agent_output_schema": descriptor.output_schema,
            "operation_policy": "optional" if is_write else "none",
            "idempotency_policy": "required" if is_write else "none",
            "consistency_policy": "strong",
            "evidence_policy": "optional",
            "audit_policy": "standard",
            "domain_errors": DOMAIN_ERRORS,
            "domain_errors_complete": True,
        }
    )


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    governed = spec.model_copy(update={"owner": "project_management", "plugin_callable": True})
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["descriptor_for", "register_capability"]
