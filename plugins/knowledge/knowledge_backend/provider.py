"""Knowledge-owned registration boundary for native Capability V2 contracts."""
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


_RESOURCE_FIELDS = {
    "knowledge.get": ("knowledge-entry", "gid"),
    "knowledge.document.get": ("knowledge-document", "document_gid"),
    "knowledge.document.acl.list": ("knowledge-document", "document_gid"),
    "knowledge.document.acl.grant": ("knowledge-document", "document_gid"),
    "knowledge.document.acl.revoke": ("knowledge-document", "document_gid"),
    "knowledge.document.diff": ("knowledge-document", "document_gid"),
    "knowledge.document.history.get": ("knowledge-document", "document_gid"),
    "knowledge.document.create": ("knowledge-space", "space_gid"),
    "knowledge.document.revise": ("knowledge-document", "document_gid"),
    "knowledge.document.restore": ("knowledge-document", "document_gid"),
    "knowledge.reference_dataset.publish": ("knowledge-reference-dataset", "dataset_gid"),
    "knowledge.proposal.get": ("knowledge-proposal", "proposal_gid"),
    "knowledge.proposal.review": ("knowledge-proposal", "proposal_gid"),
    "knowledge.proposal.outbox.retry": ("knowledge-outbox", "outbox_gid"),
    "knowledge.personalization.change.apply.atomic.recent_record": ("knowledge-item", "gid"),
}

_DOMAIN_ERRORS = (
    DomainErrorContract(
        code="resource_not_found",
        meaning="The scoped Knowledge resource does not exist or is not visible.",
    ),
    DomainErrorContract(
        code="revision_conflict",
        meaning="The document head differs from the supplied base revision.",
    ),
    DomainErrorContract(
        code="proposal_state_conflict",
        meaning="The proposal is no longer in a state that accepts this transition.",
    ),
    DomainErrorContract(
        code="knowledge_storage_unavailable",
        meaning="The immutable Knowledge object store is unavailable.",
        retryable=True,
    ),
    DomainErrorContract(
        code="publication_in_progress",
        meaning="Another worker owns the current publication lease.",
        retryable=True,
    ),
    DomainErrorContract(
        code="self_review_forbidden",
        meaning="Proposal creators cannot approve or reject their own proposal.",
    ),
    DomainErrorContract(
        code="resource_type_invalid",
        meaning="The supplied resource type is not tool, equipment, or fixture.",
    ),
    DomainErrorContract(
        code="resource_code_invalid",
        meaning="The supplied resource code is blank after normalization.",
    ),
    DomainErrorContract(
        code="mapping_batch_limit_exceeded",
        meaning="The resolver request contains more than 500 unique typed codes.",
    ),
    DomainErrorContract(
        code="mapping_candidate_limit_exceeded",
        meaning="One typed resource code has more than 100 active model mappings.",
    ),
    DomainErrorContract(
        code="mapping_snapshot_changed",
        meaning="The requested mapping snapshot is no longer current.",
    ),
    DomainErrorContract(
        code="mapping_data_invalid",
        meaning="A stored resource mapping is not a valid immutable Digital Model reference.",
    ),
    DomainErrorContract(
        code="tenant_context_required",
        meaning="Resource mappings cannot be resolved without an authenticated tenant scope.",
    ),
)


def _business_definition(spec, *, is_write: bool) -> dict[str, object]:
    operation = (
        spec.id.split(".atomic.", 1)[1].replace("_", " ")
        if ".atomic." in spec.id else spec.id.removeprefix("knowledge.").replace(".", " ")
    )
    return {
        "business_effect": (
            f"Authorized knowledge contributors can apply the requested {operation} change "
            "within their active tenant and receive its governed outcome."
            if is_write else
            f"Authorized users can inspect the requested {operation} knowledge result "
            "within their active tenant."
        ),
        "business_acceptance_criteria": (
            "The Provider evaluates the request only within the authenticated active tenant.",
            "The returned data conforms to the Capability's closed output contract.",
            (
                "The requested change is committed once, or the Provider returns a governed error without reporting success."
                if is_write else
                "The read does not mutate Knowledge business state."
            ),
        ),
        "business_invariants": (),
        "no_business_invariant_reason": (
            "This Capability introduces no additional business invariant beyond the Knowledge "
            "Provider's tenant authorization, closed schema, and transaction policies."
        ),
    }


def descriptor_for(spec):
    """Create the frozen native descriptor owned and reviewed by Knowledge."""
    descriptor = descriptor_from_provider_spec(spec)
    deprecated = bool(spec.deprecated)
    is_write = descriptor.side_effect_level is not SideEffectLevel.READ
    resource = _RESOURCE_FIELDS.get(spec.id)
    selectors = (
        (ResourceSelector(resource_type=resource[0], payload_path=resource[1]),)
        if resource else ()
    )
    updates = {
        "lifecycle_status": LifecycleStatus.DEPRECATED if deprecated else LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(
            web=True,
            api=True,
            plugin=not deprecated,
            agent=not deprecated,
            mcp=not deprecated,
            worker=spec.id in {
                "knowledge.proposal.outbox.retry", "knowledge.reference_dataset.publish",
                "knowledge.resource_model_mapping.resolve",
            },
        ),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "knowledge.v2:" + (",".join(spec.permissions) or "authenticated"),
        "resource_selectors": selectors,
        "data_classification": "confidential",
        "delegation_policy": "scoped",
        "agent_output_schema": descriptor.output_schema,
        "operation_policy": "optional" if is_write else "none",
        "concurrency_policy": (
            "expected_version"
            if spec.id in {"knowledge.document.revise", "knowledge.document.restore"}
            else "none"
        ),
        "expected_version_payload_path": (
            "base_revision_gid"
            if spec.id in {"knowledge.document.revise", "knowledge.document.restore"}
            else None
        ),
        "idempotency_policy": "required" if is_write else "none",
        # Current Knowledge repositories commit their own database/OIS unit of work.
        # Reliability therefore records an externally consistent outcome and never
        # pretends to enlist that commit in the Base outcome transaction.
        "consistency_policy": "external" if is_write else "strong",
        "evidence_policy": "required" if (
            spec.id.startswith("knowledge.document.")
            or spec.id == "knowledge.resource_model_mapping.resolve"
        ) else "optional",
        "domain_errors": _DOMAIN_ERRORS,
        "domain_errors_complete": True,
        "deprecation_message": (
            f"Use {spec.replaced_by}." if deprecated and spec.replaced_by else None
        ),
        **_business_definition(spec, is_write=is_write),
    }
    if spec.id == "knowledge.resource_model_mapping.resolve":
        updates.update({
            "business_effect": "Resolve each typed process resource code to one exact governed tool, equipment or fixture model version, returning all missing or ambiguous mappings.",
            "business_acceptance_criteria": (
                "Resolution preserves the caller-provided resource type and normalized code identity.",
                "Every resolved item contains one immutable model and model-version reference.",
                "Missing, ambiguous and over-limit mappings return governed diagnostics without selecting a candidate implicitly.",
            ),
            "business_invariants": (),
            "no_business_invariant_reason": "This read applies existing governed mappings and returns deterministic diagnostics; it does not create, choose or mutate a mapping.",
        })
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    registry.register(spec, handler, descriptor=descriptor_for(spec))


__all__ = ["descriptor_for", "register_capability"]
