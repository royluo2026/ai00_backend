"""REST adapters for the Capability Kernel (legacy and stable v1 routes)."""
from __future__ import annotations

import re
from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.capabilities.init_next import CapabilityBusinessError, CapabilityError, capability_registry
from backend.routers.deps import build_profile, get_current_user
from backend.routers.deps import get_authenticated_principal
from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    IDENTITY_PATTERN,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.policies import GatewayPolicyError


class InvokeRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)
    confirmation_token: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    expected_resource_version: str | None = Field(default=None, max_length=255)


def _correlation_id(candidate: str | None, fallback: str) -> str:
    value = (candidate or "").strip()
    return value if re.fullmatch(IDENTITY_PATTERN, value) else fallback


def _web_identity(current_user: dict, principal) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(**principal.model_dump()),
        tenant=TenantIdentity(
            tenant_id=str(current_user.get("team_id") or "default"),
            membership="member",
            active_roles=tuple(filter(None, (
                current_user.get("org_role"), current_user.get("system_role"),
            ))),
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )


_BUSINESS_ERROR_STATUS = {
    "resource_not_found": 404,
    "version_not_found": 404,
    "version_not_published": 409,
    "state_conflict": 409,
    "precondition_failed": 412,
}


def _business_error_http_exception(error: CapabilityBusinessError) -> HTTPException:
    """Compatibility mapper retained for non-V2 routes during migration."""
    payload = CapabilityError(
        code=error.code,
        message=error.message,
        retryable=error.retryable,
        details=error.details,
    )
    return HTTPException(
        status_code=_BUSINESS_ERROR_STATUS.get(error.code, 422),
        detail=payload.model_dump(mode="json"),
    )


def _build_router(prefix: str) -> APIRouter:
    api = APIRouter(prefix=prefix, tags=["capabilities"])

    @api.get("")
    def list_capabilities(
        execution: str | None = Query(default=None, pattern=r"^(cloud|local)$"),
        tag: str | None = None,
        consumer: str | None = Query(default=None, pattern=r"^(web|agent|plugin|api|mcp)$"),
        _current_user: dict = Depends(get_current_user),
    ):
        specs = capability_registry.list(execution=execution, tag=tag, plugin_callable=True if consumer == "plugin" else None)
        granted = set(build_profile(_current_user).get("permissions", []))
        specs = [spec for spec in specs if set(spec.permissions) <= granted]
        if consumer in {"agent", "api", "mcp"}:
            specs = [spec for spec in specs if not spec.deprecated]
        return {"success": True, "data": [spec.model_dump(mode="json") for spec in specs]}

    @api.get("/{capability_id}")
    def describe_capability(
        capability_id: str,
        version: int | None = Query(default=None, ge=1),
        _current_user: dict = Depends(get_current_user),
    ):
        try:
            spec = capability_registry.get(capability_id, version).spec
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "capability_not_found", "message": str(exc)}) from exc
        return {"success": True, "data": spec.model_dump(mode="json")}

    @api.post("/{capability_id}:confirm")
    async def confirm_capability(
        capability_id: str,
        body: InvokeRequest,
        request: Request,
        current_user: dict = Depends(get_current_user),
        principal = Depends(get_authenticated_principal),
    ):
        if body.version is None:
            raise HTTPException(status_code=400, detail={"code": "major_version_required"})
        generated_request_id = f"cap_{uuid.uuid4().hex}"
        request_id = _correlation_id(request.headers.get("X-Request-ID"), generated_request_id)
        trace_id = _correlation_id(request.headers.get("X-Trace-ID"), request_id)
        gateway = get_default_gateway()
        try:
            issued = await gateway.request_approval(InvocationEnvelope(
                capability_id=capability_id,
                major_version=body.version,
                catalog_release=gateway.catalog_release,
                payload=body.payload,
                identity=_web_identity(current_user, principal),
                idempotency_key=body.idempotency_key,
                expected_resource_version=body.expected_resource_version,
                request_id=request_id,
                trace_id=trace_id,
            ))
        except GatewayPolicyError as exc:
            status_code = 409 if exc.code in {"confirmation_not_required"} else 403
            if exc.code in {"catalog_resolution_failed", "invalid_input"}:
                status_code = 400
            if exc.code in {
                "approval_service_failed", "approval_service_unavailable",
                "transaction_participant_required",
            }:
                status_code = 503
            raise HTTPException(
                status_code=status_code, detail={"code": exc.code, "message": exc.message}
            ) from exc
        return {"success": True, "data": {
            "confirmation_token": issued.token,
            "expires_at": issued.challenge.expires_at.isoformat(),
            "capability_id": issued.challenge.capability_id,
            "version": issued.challenge.major_version,
            "approval_id": issued.challenge.approval_id,
        }}

    @api.post("/{capability_id}:invoke")
    async def invoke_capability(
        capability_id: str,
        body: InvokeRequest,
        request: Request,
        current_user: dict = Depends(get_current_user),
        principal = Depends(get_authenticated_principal),
    ):
        if body.version is None:
            raise HTTPException(status_code=400, detail={"code": "major_version_required"})
        generated_request_id = f"cap_{uuid.uuid4().hex}"
        request_id = _correlation_id(request.headers.get("X-Request-ID"), generated_request_id)
        trace_id = _correlation_id(request.headers.get("X-Trace-ID"), request_id)
        gateway = get_default_gateway()
        identity = _web_identity(current_user, principal)
        result = await gateway.invoke(InvocationEnvelope(
            capability_id=capability_id,
            major_version=body.version,
            catalog_release=gateway.catalog_release,
            payload=body.payload,
            identity=identity,
            idempotency_key=body.idempotency_key,
            expected_resource_version=body.expected_resource_version,
            approval_reference=body.confirmation_token,
            request_id=request_id,
            trace_id=trace_id,
        ))
        return {"success": result.ok, "data": result.model_dump(mode="json")}

    return api


router = APIRouter()
router.include_router(_build_router("/api/capabilities"))
router.include_router(_build_router("/api/v1/capabilities"))
