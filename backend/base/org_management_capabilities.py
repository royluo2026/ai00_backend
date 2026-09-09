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


def _tenant(context: object) -> str:
    return str(getattr(context, "team_gid", None) or f"user:{getattr(context, 'user_gid', '')}")


def _active_principal_provider(payload: dict[str, Any], _context: object) -> dict[str, Any]:
    from backend.base.active_principal import get_active_principal
    value = get_active_principal(payload["user_gid"])
    if value is None:
        raise CapabilityBusinessError("resource_not_found", "人员不存在或已停用")
    return {"data": value}


async def _validated_project_tenant(
    context: object, project_gid: str, *, validation: object | None = None
) -> str:
    from datetime import UTC, datetime
    from backend.capability_v2.contracts import CorrelationRef
    from backend.capability_v2.delegation import InMemoryDelegationStore
    from backend.capability_v2.domain_client import DomainInvocation
    from backend.capability_v2.identity import AuthenticatedPrincipal, IdentityBroker, InMemoryMountStore
    from backend.capability_v2.official_service_grants import official_service_identities
    service_id = "base-project-validator"
    tenant_gid = _tenant(context)
    if validation is None:
        with official_service_identities.trusted_tenant(
            service_id=service_id, tenant_id=tenant_gid, source_kind="authenticated_request",
            source_ref=str(getattr(context, "request_id", "manager-replace")),
        ):
            identity = IdentityBroker(
                official_service_identities, InMemoryDelegationStore(), InMemoryMountStore()
            ).for_local_runtime(
                AuthenticatedPrincipal(service_id=service_id, authentication_method="internal",
                                       authenticated_at=datetime.now(UTC)),
                tenant_id=tenant_gid, runtime_id=service_id,
            )
            validation = await context.domain_client.invoke(
                DomainInvocation(capability_id="project.project.validation.get", major_version=1,
                                 payload={"project_gid": project_gid}),
                identity,
                CorrelationRef(request_id=str(getattr(context, "request_id", "manager-replace")),
                               trace_id=str(getattr(context, "request_id", "manager-replace"))),
            )
    if not validation.ok:
        code = validation.error.code if validation.error else "provider_unavailable"
        raise CapabilityBusinessError(code, validation.error.message if validation.error else "项目校验失败")
    data = validation.data or {}
    project = data.get("data", data) if isinstance(data, dict) else {}
    owner_tenant = str(project.get("team_id") or "")
    if not owner_tenant:
        raise CapabilityBusinessError("provider_unavailable", "项目校验未返回所属租户")
    return owner_tenant


async def _manager_read_provider(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.project_responsibility import ProjectManagerService
    tenant_gid = await _validated_project_tenant(context, payload["project_gid"])
    return {"data": ProjectManagerService().read(tenant_gid, payload["project_gid"])}


async def _manager_replace_provider(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.project_responsibility import ProjectManagerError, ProjectManagerService
    try:
        tenant_gid = await _validated_project_tenant(context, payload["project_gid"])
        value = ProjectManagerService().replace(
            tenant_gid=tenant_gid, actor_gid=str(getattr(context, "user_gid", "")),
            project_gid=payload["project_gid"], user_gids=payload["user_gids"],
            expected_revision=payload["expected_revision"],
            idempotency_key=payload["idempotency_key"],
        )
    except ProjectManagerError as exc:
        raise CapabilityBusinessError(exc.code, str(exc)) from exc
    return {"data": value}


def _bop_authorization_provider(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.bop_edit_authorization import check_bop_edit
    return {"data": check_bop_edit(
        tenant_gid=_tenant(context), user_gid=str(getattr(context, "user_gid", "")),
        active_roles=tuple(getattr(context, "active_roles", ()) or ()),
        project_gid=payload["project_gid"], line_gid=payload.get("line_gid"),
    )}


def _projection_apply_provider(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.line_responsibility_projection import apply_projection
    from backend.base.project_responsibility import ProjectManagerError
    try:
        return {"data": apply_projection(payload, tenant_gid=_tenant(context),
                                          actor_gid=str(getattr(context, "user_gid", "")))}
    except ProjectManagerError as exc:
        raise CapabilityBusinessError(exc.code, str(exc)) from exc


def _projection_get_provider(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.line_responsibility_projection import get_projection
    value = get_projection(payload["operation_gid"], tenant_gid=_tenant(context))
    if value is None:
        raise CapabilityBusinessError("resource_not_found", "投影操作不存在")
    return {"data": value}


def _descriptor(
    spec: CapabilitySpec,
    *,
    business_effect: str,
    enforcement_ref: str,
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
        "business_effect": business_effect,
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
                enforcement_ref=enforcement_ref,
                error_code="permission_denied",
                test_refs=(
                    f"backend/tests/acceptance/test_mandatory_cases.py::test_success_case[{spec.id}@1]",
                ),
            ),
        ),
        "no_business_invariant_reason": None,
    })


def _register(
    registry: Any,
    *,
    capability_id: str,
    description: str,
    business_effect: str,
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
    registry.register(spec, handler, descriptor=_descriptor(
        spec,
        business_effect=business_effect,
        enforcement_ref=f"backend/base/org_management_capabilities.py:{handler.__name__}",
        exposure=resolved_exposure,
        consistency="external" if write else "strong",
    ))


def register_org_management_capabilities(registry: Any) -> None:
    principal = _object({"gid": ID, "name": {"type": "string", "maxLength": 256}, "avatar_url": {"type": "string", "maxLength": 2048}, "is_active": {"type": "boolean"}}, ("gid", "name", "avatar_url", "is_active"))
    _register(
        registry,
        capability_id="base.identity.active_principal.get",
        description="Return one minimal active-principal projection by Base user GID.",
        business_effect="Supplies the active Base identity required to assign organization responsibilities without exposing a full user record.",
        input_schema=_object({"user_gid": ID}, ("user_gid",)),
        output_schema=_object({"data": principal}, ("data",)), handler=_active_principal_provider,
    )
    manager = _object({"gid": ID, "name": {"type": "string", "maxLength": 256}, "avatar_url": {"type": "string", "maxLength": 2048}}, ("gid", "name", "avatar_url"))
    manager_data = _object({"project_gid": ID, "revision": {"type": "integer", "minimum": 0}, "managed": {"type": "boolean"}, "managers": {"type": "array", "items": manager, "maxItems": 50}}, ("project_gid", "revision", "managed", "managers"))
    _register(registry, capability_id="base.project_manager.read", description="Read the authoritative bounded project-manager set.", business_effect="Returns the tenant-authoritative manager assignment and revision used by organization administration.", input_schema=_object({"project_gid": ID}, ("project_gid",)), output_schema=_object({"data": manager_data}, ("data",)), handler=_manager_read_provider)
    _register(registry, capability_id="base.project_manager.replace", description="Replace the authoritative project-manager set after super-admin confirmation.", business_effect="Commits a confirmed, revision-checked replacement of the tenant-authoritative project manager assignment.", input_schema=_object({"project_gid": ID, "user_gids": {"type": "array", "items": ID, "maxItems": 50, "uniqueItems": True}, "expected_revision": {"type": "integer", "minimum": 0}, "idempotency_key": ID}, ("project_gid", "user_gids", "expected_revision", "idempotency_key")), output_schema=_object({"data": manager_data}, ("data",)), write=True, handler=_manager_replace_provider)
    projection_input = _object({"operation_gid": ID, "source_gid": ID, "source_revision": {"type": "integer", "minimum": 1}, "project_gid": ID, "bop_line_gid": NULL_ID, "user_gids": {"type": "array", "items": ID, "maxItems": 50, "uniqueItems": True}, "idempotency_key": ID}, ("operation_gid", "source_gid", "source_revision", "project_gid", "bop_line_gid", "user_gids", "idempotency_key"))
    projection_data = _object({"operation_gid": ID, "source_revision": {"type": "integer", "minimum": 1}, "status": {"type": "string", "enum": ["completed"]}}, ("operation_gid", "source_revision", "status"))
    worker = ExposurePolicy(worker=True)
    _register(registry, capability_id="base.project_responsibility.projection.apply", description="Apply one idempotent source-scoped BOP line responsibility projection.", business_effect="Materializes the latest approved manual-line responsibility as idempotent Base authorization grants.", input_schema=projection_input, output_schema=_object({"data": projection_data}, ("data",)), write=True, exposure=worker, handler=_projection_apply_provider)
    _register(registry, capability_id="base.project_responsibility.projection.get", description="Read one source-scoped BOP line projection status.", business_effect="Reports whether a specific responsibility projection has durably completed for its source revision.", input_schema=_object({"operation_gid": ID}, ("operation_gid",)), output_schema=_object({"data": projection_data}, ("data",)), exposure=worker, handler=_projection_get_provider)
    auth_data = _object({"allowed": {"type": "boolean"}, "scope": {"type": "string", "enum": ["global", "project", "line", "none"]}, "reason": {"type": "string", "maxLength": 256}}, ("allowed", "scope", "reason"))
    _register(registry, capability_id="base.bop_edit.authorization.check", description="Check one trusted actor's project or line-scoped BOP edit authority.", business_effect="Produces the authoritative Base decision that permits or denies a BOP edit at project or line scope.", input_schema=_object({"project_gid": ID, "line_gid": NULL_ID}, ("project_gid", "line_gid")), output_schema=_object({"data": auth_data}, ("data",)), exposure=ExposurePolicy(local_runtime=True), handler=_bop_authorization_provider)


__all__ = ["register_org_management_capabilities"]
