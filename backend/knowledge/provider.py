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
from backend.capability_v2.v1_adapter import adapt_v1_spec


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
    "knowledge.proposal.get": ("knowledge-proposal", "proposal_gid"),
    "knowledge.proposal.review": ("knowledge-proposal", "proposal_gid"),
    "knowledge.proposal.outbox.retry": ("knowledge-outbox", "outbox_gid"),
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
)


def descriptor_for(spec):
    """Create the frozen native descriptor owned and reviewed by Knowledge."""
    descriptor = adapt_v1_spec(spec)
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
            worker=spec.id == "knowledge.proposal.outbox.retry",
        ),
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
        "evidence_policy": "required" if spec.id.startswith("knowledge.document.") else "optional",
        "domain_errors": _DOMAIN_ERRORS,
        "domain_errors_complete": True,
        "deprecation_message": (
            f"Use {spec.replaced_by}." if deprecated and spec.replaced_by else None
        ),
    }
    return CapabilityDescriptorV2.model_validate({**descriptor.model_dump(), **updates})


def register_capability(registry: Any, spec: Any, handler: Any) -> None:
    registry.register(spec, handler, descriptor=descriptor_for(spec))


__all__ = ["descriptor_for", "register_capability"]
