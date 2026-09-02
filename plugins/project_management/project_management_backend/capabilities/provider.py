"""Native stable descriptors for the reviewed Project Management surface."""
from __future__ import annotations

import hashlib
from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    DomainErrorContract,
    ExposurePolicy,
    LifecycleStatus,
    SideEffectLevel,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec


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

# These IDs were approved in the historical catalog but have no Project
# application outcome or repository port. Keep their identity discoverable,
# but remove them from the stable invocation surface until implemented.
DEPRECATED_CAPABILITY_IDS = frozenset({
    "project.activity.aggregate",
    "project.bitable_binding.change.apply",
    "project.bitable_binding.read",
    "project.craft_scope.read",
})


def descriptor_for(spec: Any) -> CapabilityDescriptorV2:
    descriptor = descriptor_from_provider_spec(spec)
    capability_version_gid = "cv2_" + hashlib.sha256(
        f"{descriptor.id}@{descriptor.major_version}:{descriptor.schema_hash}".encode("utf-8")
    ).hexdigest()[:24]
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    is_approval_rejection = spec.id == "project.approval.order.reject" and spec.version == 1
    return CapabilityDescriptorV2.model_validate(
        {
            **descriptor.model_dump(),
            "capability_version_gid": capability_version_gid,
            "lifecycle_status": (
                LifecycleStatus.DEPRECATED
                if spec.id in DEPRECATED_CAPABILITY_IDS
                else LifecycleStatus.STABLE
            ),
            "deprecation_message": (
                "Approved legacy identity retained for compatibility; no governed "
                "Project application outcome is currently registered."
                if spec.id in DEPRECATED_CAPABILITY_IDS else None
            ),
            "exposure": ExposurePolicy(
                web=True, api=True, plugin=True, agent=True, mcp=True
            ),
            "exposure_policy_source": "provider_explicit",
            "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
            "authorization_policy": "project_management.v2:"
            + (",".join(spec.permissions) or "authenticated"),
            "data_classification": "confidential",
            "delegation_policy": "scoped",
            "agent_output_schema": descriptor.output_schema,
            "operation_policy": "none" if is_approval_rejection else ("optional" if is_write else "none"),
            "replay_data_policy": "projected" if is_approval_rejection else "metadata_only",
            "idempotency_policy": "required" if is_write else "none",
            # The domain commits its own OceanBase transaction and cannot
            # enlist the platform outcome store in that same connection.
            "consistency_policy": "external" if is_write else "strong",
            "evidence_policy": "optional",
            "audit_policy": "standard",
            "concurrency_policy": "expected_version" if is_approval_rejection else "none",
            "expected_version_payload_path": "expected_revision" if is_approval_rejection else None,
            "domain_errors": DOMAIN_ERRORS,
            "domain_errors_complete": True,
        }
    )


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    governed = spec.model_copy(update={"owner": "project_management", "plugin_callable": True})
    registry.register(governed, handler, descriptor=descriptor_for(governed))


__all__ = ["DEPRECATED_CAPABILITY_IDS", "descriptor_for", "register_capability"]
