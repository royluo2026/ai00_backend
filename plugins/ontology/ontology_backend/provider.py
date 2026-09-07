from __future__ import annotations

from backend.capability_v2.contracts import AutomationLevel, BusinessInvariantContract, CapabilityDescriptorV2, DomainErrorContract, ExposurePolicy, LifecycleStatus, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec

ERRORS = (
    DomainErrorContract(code="resource_not_found", meaning="Ontology release or object was not found."),
    DomainErrorContract(code="approval_required", meaning="Activation requires an approved release."),
    DomainErrorContract(code="version_conflict", meaning="Ontology active release changed concurrently."),
    DomainErrorContract(code="provider_unavailable", meaning="Ontology provider is unavailable.", retryable=True),
)

_READ_V2_BUSINESS = {
    "ontology.concept.get": (
        "Consumers obtain the effective schema of one immutable ontology concept, including ancestor-owned properties and relations, or its typed summary.",
        (
            "Schema members are gathered only from the resolved release and ordered from ancestors to the requested concept.",
            "The requested stable identity and kind select one object; a missing object fails instead of resolving another identity.",
            "The closed result and its concept reference identify the same immutable release and content hash.",
        ),
        "test_v2_schema_inherits_members_from_the_same_immutable_release",
    ),
    "ontology.concept.resolve": (
        "Consumers receive a typed ontology identity resolution that preserves ambiguity and offers at most twenty candidates from one immutable release.",
        (
            "Unique exact matches resolve deterministically; multiple matches remain ambiguous and never select an arbitrary concept.",
            "The result includes no more than twenty typed candidate summaries while retaining the ambiguous or candidate status.",
            "Resolved concepts and candidates retain the selected release and content hash.",
        ),
        "test_v2_resolution_keeps_ambiguity_and_bounds_candidates",
    ),
    "ontology.object.list": (
        "Consumers browse a typed page of immutable ontology objects with their exact release references, total count and deterministic page position.",
        (
            "Only requested supported object kinds from one resolved release are returned.",
            "Pages contain at most the requested limit, which cannot exceed one hundred, and retain total and offset.",
            "Every returned object's concept reference matches the release and content hash of the page.",
        ),
        "test_v2_list_is_paged_and_release_pinned",
    ),
}

def descriptor_for(spec):
    base = descriptor_from_provider_spec(spec); write = base.side_effect_level is not SideEffectLevel.READ
    business = {}
    if spec.version == 2 and spec.id in _READ_V2_BUSINESS:
        effect, criteria, test_name = _READ_V2_BUSINESS[spec.id]
        handler = {
            "ontology.concept.get": "get_concept",
            "ontology.concept.resolve": "resolve_concept_v2",
            "ontology.object.list": "list_objects",
        }[spec.id]
        business = {
            "business_effect": effect,
            "business_acceptance_criteria": criteria,
            "business_invariants": (BusinessInvariantContract(
                rule_id=f"{spec.id}.release_projection", version=1,
                statement=criteria[0],
                applies_when=f"{spec.id}@2 returns a result",
                enforcement_ref=f"plugins/ontology/ontology_backend/capabilities/ontology_concepts_next.py:{handler}",
                error_code="resource_not_found",
                test_refs=(f"backend/tests/test_ontology_read_versions.py::{test_name}",),
            ),),
            "no_business_invariant_reason": None,
        }
    return CapabilityDescriptorV2.model_validate({
        **base.model_dump(), **business, "owner_domain": "ontology", "lifecycle_status": LifecycleStatus.STABLE,
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
