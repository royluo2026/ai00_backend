"""Native governed Descriptor conversion for Factory."""
from __future__ import annotations

from backend.capability_v2.contracts import AutomationLevel, CapabilityDescriptorV2, DomainErrorContract, ExposurePolicy, LifecycleStatus, SideEffectLevel
from backend.capability_v2.v1_adapter import adapt_v1_spec


ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable) for code, meaning, retryable in (
    ("invalid_input", "The Factory request is invalid.", False),
    ("resource_not_found", "The Factory resource does not exist.", False),
    ("permission_denied", "The caller cannot access the Factory tenant.", False),
    ("version_conflict", "The Factory resource changed concurrently.", False),
    ("approval_required", "The Factory change requires approval.", False),
    ("provider_unavailable", "The Factory provider is unavailable.", True),
))


def descriptor_for(spec) -> CapabilityDescriptorV2:
    base = adapt_v1_spec(spec)
    write = base.side_effect_level is not SideEffectLevel.READ
    return CapabilityDescriptorV2.model_validate({
        **base.model_dump(),
        "owner_domain": "factory",
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "automation_level": AutomationLevel.A0 if spec.id == "factory.asset.scrap" else (AutomationLevel.A1 if write else AutomationLevel.A2),
        "authorization_policy": "factory.v2:" + ",".join(spec.permissions),
        "data_classification": "confidential", "delegation_policy": "scoped",
        "agent_output_schema": base.output_schema,
        "operation_policy": "required" if spec.id == "factory.asset.scrap" else ("optional" if write else "none"),
        "idempotency_policy": "required" if write else "none",
        "consistency_policy": "strong", "evidence_policy": "required" if spec.id == "factory.asset.scrap" else "optional",
        "audit_policy": "high_risk" if spec.id == "factory.asset.scrap" else "standard",
        "domain_errors": ERRORS, "domain_errors_complete": True,
    })
