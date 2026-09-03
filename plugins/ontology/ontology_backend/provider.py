from __future__ import annotations

from backend.capability_v2.contracts import AutomationLevel, CapabilityDescriptorV2, DomainErrorContract, ExposurePolicy, LifecycleStatus, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec

ERRORS = (
    DomainErrorContract(code="resource_not_found", meaning="Ontology release or object was not found."),
    DomainErrorContract(code="approval_required", meaning="Activation requires an approved release."),
    DomainErrorContract(code="version_conflict", meaning="Ontology active release changed concurrently."),
    DomainErrorContract(code="provider_unavailable", meaning="Ontology provider is unavailable.", retryable=True),
)

def descriptor_for(spec):
    base = descriptor_from_provider_spec(spec); write = base.side_effect_level is not SideEffectLevel.READ
    return CapabilityDescriptorV2.model_validate({
        **base.model_dump(), "owner_domain": "ontology", "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(
            web=True, api=True, plugin=True,
            agent=spec.id != "ontology.release.activate",
            mcp=spec.id != "ontology.release.activate",
        ),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A0 if spec.id == "ontology.release.activate" else (AutomationLevel.A1 if write else AutomationLevel.A2),
        "authorization_policy": "ontology.v2:" + (",".join(spec.permissions) or "authenticated"),
        "data_classification": "confidential", "delegation_policy": "scoped", "agent_output_schema": base.output_schema,
        "operation_policy": "required" if spec.id == "ontology.release.activate" else ("optional" if write else "none"),
        "idempotency_policy": "required" if write else "none", "consistency_policy": "external" if write else "strong",
        "evidence_policy": "required" if write else "optional", "audit_policy": "high_risk" if spec.id == "ontology.release.activate" else "standard",
        "domain_errors": ERRORS, "domain_errors_complete": True,
    })


class GovernedRegistry:
    def __init__(self, target): self.target = target
    def register(self, spec, handler, *, descriptor=None):
        self.target.register(spec, handler, descriptor=descriptor or descriptor_for(spec))
