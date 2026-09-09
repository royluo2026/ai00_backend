"""Governed Base contracts for manually maintained organization responsibilities."""
from __future__ import annotations

from typing import Any, Callable

from backend.capability_v2.contracts import (
    AutomationLevel,
    BusinessInvariantContract,
    CapabilityDescriptorV2,
    DomainErrorContract,
    ExposurePolicy,
    LifecycleStatus,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityRisk,
    CapabilitySpec,
)


ID = {"type": "string", "minLength": 1, "maxLength": 256}
NULL_ID = {"type": ["string", "null"], "maxLength": 256}
ERRORS = tuple(
    DomainErrorContract(code=code, meaning=meaning, retryable=retryable)
    for code, meaning, retryable in (
        ("invalid_input", "The closed Base request is invalid.", False),
        ("permission_denied", "The actor cannot perform this Base operation.", False),
        ("resource_not_found", "The Base resource does not exist or is inactive.", False),
        ("version_conflict", "The aggregate revision changed.", False),
        ("idempotency_conflict", "The idempotency key belongs to another payload.", False),
        ("provider_unavailable", "A required owning-domain provider is unavailable.", True),
    )
)


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _pending(_payload: dict[str, Any], _context: object) -> dict[str, Any]:
    raise CapabilityBusinessError(
        "provider_unavailable", "The Base responsibility provider is not bound yet.", retryable=True
    )


def _descriptor(
    spec: CapabilitySpec,
    *,
    exposure: ExposurePolicy,
    consistency: str = "strong",
) -> CapabilityDescriptorV2:
    base = descriptor_from_provider_spec(spec)
    is_write = spec.risk == CapabilityRisk.WRITE
    return CapabilityDescriptorV2.model_validate({
        **base.model_dump(),
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": exposure,
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if is_write else AutomationLevel.A2,
        "authorization_policy": "base.org_management:" + (",".join(spec.permissions) or "authenticated"),
        "data_classification": "confidential",
        "delegation_policy": "scoped",
        "agent_output_schema": spec.output_schema,
        "operation_policy": "optional" if is_write else "none",
        "idempotency_policy": "required" if is_write else "none",
        "consistency_policy": consistency,
        "evidence_policy": "optional",
        "audit_policy": "standard",
        "domain_errors": ERRORS,
        "domain_errors_complete": True,
        "business_effect": spec.description,
        "business_acceptance_criteria": (
            "The authenticated tenant and actor are derived by the Gateway.",
            "The result conforms to the closed Base contract.",
            "A rejected operation reports no successful responsibility change.",
        ),
        "business_invariants": (
            BusinessInvariantContract(
                rule_id=spec.id + ".tenant_scope",
                version=1,
                statement="Responsibility state is isolated to the authenticated tenant.",
                applies_when="The capability is invoked.",
                enforcement_ref="backend/base/org_management_capabilities.py",
                error_code="permission_denied",
                test_refs=("backend/tests/test_org_management_capability_contracts.py",),
            ),
        ),
        "no_business_invariant_reason": None,
    })


def _register(
    registry: Any,
    *,
    capability_id: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    write: bool = False,
    exposure: ExposurePolicy | None = None,
    handler: Callable[[dict[str, Any], object], dict[str, Any]] = _pending,
) -> None:
    spec = CapabilitySpec(
        id=capability_id,
        version=1,
        owner="base",
        description=description,
        use_when="The management center needs this exact Base-owned responsibility outcome.",
        do_not_use_when="The resource belongs to Project or Craft.",
        risk=CapabilityRisk.WRITE if write else CapabilityRisk.READ,
        confirmation="user" if write and capability_id == "base.project_manager.replace" else "none",
        idempotent=True,
        permissions=("system.user.manage",) if write else ("base.read",),
        input_schema=input_schema,
        output_schema=output_schema,
        tags=("base", "org_management", "write" if write else "read"),
    )
    resolved_exposure = exposure or ExposurePolicy(web=True, api=True, plugin=False, agent=False, mcp=False)
    registry.register(spec, handler, descriptor=_descriptor(spec, exposure=resolved_exposure, consistency="external" if write else "strong"))


def register_org_management_capabilities(registry: Any) -> None:
    principal = _object({"gid": ID, "name": {"type": "string", "maxLength": 256}, "avatar_url": {"type": "string", "maxLength": 2048}, "is_active": {"type": "boolean"}}, ("gid", "name", "avatar_url", "is_active"))
    _register(
        registry,
        capability_id="base.identity.active_principal.get",
        description="Return one minimal active-principal projection by Base user GID.",
        input_schema=_object({"user_gid": ID}, ("user_gid",)),
        output_schema=_object({"data": principal}, ("data",)),
    )
    manager = _object({"gid": ID, "name": {"type": "string", "maxLength": 256}, "avatar_url": {"type": "string", "maxLength": 2048}}, ("gid", "name", "avatar_url"))
    manager_data = _object({"project_gid": ID, "revision": {"type": "integer", "minimum": 0}, "managed": {"type": "boolean"}, "managers": {"type": "array", "items": manager, "maxItems": 50}}, ("project_gid", "revision", "managed", "managers"))
    _register(registry, capability_id="base.project_manager.read", description="Read the authoritative bounded project-manager set.", input_schema=_object({"project_gid": ID}, ("project_gid",)), output_schema=_object({"data": manager_data}, ("data",)))
    _register(registry, capability_id="base.project_manager.replace", description="Replace the authoritative project-manager set after super-admin confirmation.", input_schema=_object({"project_gid": ID, "user_gids": {"type": "array", "items": ID, "maxItems": 50, "uniqueItems": True}, "expected_revision": {"type": "integer", "minimum": 0}, "idempotency_key": ID}, ("project_gid", "user_gids", "expected_revision", "idempotency_key")), output_schema=_object({"data": manager_data}, ("data",)), write=True)
    projection_input = _object({"operation_gid": ID, "source_gid": ID, "source_revision": {"type": "integer", "minimum": 1}, "project_gid": ID, "bop_line_gid": NULL_ID, "user_gids": {"type": "array", "items": ID, "maxItems": 50, "uniqueItems": True}, "idempotency_key": ID}, ("operation_gid", "source_gid", "source_revision", "project_gid", "bop_line_gid", "user_gids", "idempotency_key"))
    projection_data = _object({"operation_gid": ID, "source_revision": {"type": "integer", "minimum": 1}, "status": {"type": "string", "enum": ["completed"]}}, ("operation_gid", "source_revision", "status"))
    worker = ExposurePolicy(worker=True)
    _register(registry, capability_id="base.project_responsibility.projection.apply", description="Apply one idempotent source-scoped BOP line responsibility projection.", input_schema=projection_input, output_schema=_object({"data": projection_data}, ("data",)), write=True, exposure=worker)
    _register(registry, capability_id="base.project_responsibility.projection.get", description="Read one source-scoped BOP line projection status.", input_schema=_object({"operation_gid": ID}, ("operation_gid",)), output_schema=_object({"data": projection_data}, ("data",)), exposure=worker)
    auth_data = _object({"allowed": {"type": "boolean"}, "scope": {"type": "string", "enum": ["global", "project", "line", "none"]}, "reason": {"type": "string", "maxLength": 256}}, ("allowed", "scope", "reason"))
    _register(registry, capability_id="base.bop_edit.authorization.check", description="Check one trusted actor's project or line-scoped BOP edit authority.", input_schema=_object({"project_gid": ID, "line_gid": NULL_ID}, ("project_gid", "line_gid")), output_schema=_object({"data": auth_data}, ("data",)), exposure=ExposurePolicy(local_runtime=True))


__all__ = ["register_org_management_capabilities"]
