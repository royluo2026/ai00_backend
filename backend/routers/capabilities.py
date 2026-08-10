"""REST adapters for the Capability Kernel (legacy and stable v1 routes)."""
from __future__ import annotations

import re
from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.capabilities.init_next import CapabilityBusinessError, CapabilityError, capability_registry
from backend.capabilities.confirmation_next import confirmation_manager
from backend.capabilities.validation_next import validate_payload
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


class InvokeRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)
    confirmation_token: str | None = None


def _correlation_id(candidate: str | None, fallback: str) -> str:
    value = (candidate or "").strip()
    return value if re.fullmatch(IDENTITY_PATTERN, value) else fallback


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
    def confirm_capability(
        capability_id: str,
        body: InvokeRequest,
        current_user: dict = Depends(get_current_user),
    ):
        try:
            item = capability_registry.get(capability_id, body.version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "capability_not_found", "message": str(exc)}) from exc
        if item.spec.confirmation == "none":
            raise HTTPException(status_code=400, detail={"code": "confirmation_not_required", "message": "该能力不需要确认"})
        try:
            validate_payload(dict(item.spec.input_schema), body.payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "invalid_payload", "message": str(exc)}) from exc
        permissions = tuple(build_profile(current_user).get("permissions", []))
        missing = sorted(set(item.spec.permissions) - set(permissions))
        if missing:
            raise HTTPException(status_code=403, detail={"code": "permission_denied", "missing": missing})
        token = confirmation_manager.issue(item.spec.id, item.spec.version, current_user["gid"], body.payload)
        return {"success": True, "data": {"confirmation_token": token, "expires_in": confirmation_manager.ttl_seconds, "capability_id": item.spec.id, "version": item.spec.version}}

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
        identity = ConsumerIdentity(
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
        result = await gateway.invoke(InvocationEnvelope(
            capability_id=capability_id,
            major_version=body.version,
            catalog_release=gateway.catalog_release,
            payload=body.payload,
            identity=identity,
            approval_reference=body.confirmation_token,
            request_id=request_id,
            trace_id=trace_id,
        ))
        return {"success": result.ok, "data": result.model_dump(mode="json")}

    return api


router = APIRouter()
router.include_router(_build_router("/api/capabilities"))
router.include_router(_build_router("/api/v1/capabilities"))
