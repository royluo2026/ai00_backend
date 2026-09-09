"""Project Management contracts for the manual responsibility tree."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel, BusinessInvariantContract, CapabilityDescriptorV2,
    DomainErrorContract, ExposurePolicy, LifecycleStatus,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityRisk, CapabilitySpec


ID = {"type": "string", "minLength": 1, "maxLength": 256}
ERRORS = tuple(DomainErrorContract(code=code, meaning=code.replace("_", " "), retryable=retryable) for code, retryable in (
    ("invalid_input", False), ("permission_denied", False), ("resource_not_found", False),
    ("version_conflict", False), ("idempotency_conflict", False),
    ("projection_pending", True), ("projection_failed", True), ("provider_unavailable", True),
))


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _pending(_payload: dict[str, Any], _context: object) -> dict[str, Any]:
    raise CapabilityBusinessError("provider_unavailable", "Project org-management provider is not bound.", retryable=True)


def _register(registry: Any, spec: CapabilitySpec, exposure: ExposurePolicy) -> None:
    descriptor = descriptor_from_provider_spec(spec)
    write = spec.risk == CapabilityRisk.WRITE
    descriptor = CapabilityDescriptorV2.model_validate({
        **descriptor.model_dump(),
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": exposure,
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if write else AutomationLevel.A2,
        "authorization_policy": "project.org_management:" + ",".join(spec.permissions),
        "data_classification": "confidential",
        "delegation_policy": "scoped",
        "agent_output_schema": spec.output_schema,
        "operation_policy": "optional" if write else "none",
        "idempotency_policy": "required" if write else "none",
        "consistency_policy": "external" if write else "strong",
        "evidence_policy": "optional",
        "audit_policy": "standard",
        "concurrency_policy": "expected_version" if write else "none",
        "expected_version_payload_path": "expected_revision" if write else None,
        "domain_errors": ERRORS,
        "domain_errors_complete": True,
        "business_effect": spec.description,
        "business_acceptance_criteria": (
            "The result is tenant scoped and schema closed.",
            "Only a super administrator may change the responsibility tree.",
            "Projection state is reported without false success.",
        ),
        "business_invariants": (BusinessInvariantContract(
            rule_id=spec.id + ".manual_authority", version=1,
            statement="Only explicitly stored manual responsibility data is authoritative.",
            applies_when="The capability is invoked.",
            enforcement_ref="plugins/project_management/project_management_backend/capabilities/org_management.py",
            error_code="permission_denied",
            test_refs=("backend/tests/test_org_management_capability_contracts.py",),
        ),),
        "no_business_invariant_reason": None,
    })
    registry.register(spec, _pending, descriptor=descriptor)


def register_org_management_capabilities(registry: Any) -> None:
    common = dict(owner="project_management", version=1, idempotent=True, plugin_callable=False, tags=("project_management", "org_management"))
    _register(registry, CapabilitySpec(
        id="project.project.validation.get", description="Return a minimal project identity projection for the fixed Base validator.",
        use_when="Base validates a project before replacing its manager set.", do_not_use_when="A user needs normal project detail.",
        risk=CapabilityRisk.READ, confirmation="none", permissions=("project.view",),
        input_schema=_object({"project_gid": ID}, ("project_gid",)),
        output_schema=_object({"data": _object({"gid": ID, "team_id": ID, "is_deleted": {"type": "boolean"}}, ("gid", "team_id", "is_deleted"))}, ("data",)),
        **common,
    ), ExposurePolicy(local_runtime=True))
    tree_item = _object({"gid": ID, "name": {"type": "string", "maxLength": 512}, "revision": {"type": "integer", "minimum": 0}}, ("gid", "name", "revision"))
    _register(registry, CapabilitySpec(
        id="project.org_management.read", description="Read bounded project responsibility tree, matrix, or operation status.",
        use_when="The super-admin management center reads manual project responsibilities.", do_not_use_when="The caller needs ordinary project members.",
        risk=CapabilityRisk.READ, confirmation="none", permissions=("project.view",),
        input_schema=_object({"operation": {"type": "string", "enum": ["responsibility_tree.search", "responsibility_matrix.get", "operation.get"]}, "arguments": _object({"project_gid": {"type": ["string", "null"], "maxLength": 256}, "cursor": {"type": ["string", "null"], "maxLength": 512}, "page_size": {"type": "integer", "minimum": 1, "maximum": 100}, "operation_gid": {"type": ["string", "null"], "maxLength": 256}})}, ("operation", "arguments")),
        output_schema=_object({"data": _object({"items": {"type": "array", "items": tree_item, "maxItems": 100}, "next_cursor": {"type": ["string", "null"], "maxLength": 512}} , ("items", "next_cursor"))}, ("data",)),
        **common,
    ), ExposurePolicy(web=True, api=True))
    _register(registry, CapabilitySpec(
        id="project.org_management.change.apply", description="Apply one revisioned manual-line change and durably project its BOP responsibility grants.",
        use_when="A super administrator changes one manual project line.", do_not_use_when="The caller changes ordinary project membership.",
        risk=CapabilityRisk.WRITE, confirmation="user", permissions=("system.user.manage",),
        input_schema=_object({"operation": {"type": "string", "enum": ["managed_line.create", "managed_line.update", "managed_line.delete", "projection.retry"]}, "arguments": _object({}), "expected_revision": {"type": "integer", "minimum": 0}, "idempotency_key": ID}, ("operation", "arguments", "expected_revision", "idempotency_key")),
        output_schema=_object({"data": _object({"operation_gid": ID, "revision": {"type": "integer", "minimum": 1}, "status": {"type": "string", "enum": ["pending_projection", "completed", "failed_retryable", "failed_terminal"]}}, ("operation_gid", "revision", "status"))}, ("data",)),
        **common,
    ), ExposurePolicy(web=True, api=True))


__all__ = ["register_org_management_capabilities"]
