"""REST adapters for the Capability Kernel (legacy and stable v1 routes)."""
from __future__ import annotations

import re
import json
from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict, model_validator
from backend.capability_v2.identity import CONSUMER_IDENTITY_FIELDS

from backend.capabilities.init_next import CapabilityBusinessError, CapabilityError, capability_registry
from backend.routers.deps import build_profile, get_current_user
from backend.routers.deps import get_authenticated_principal
from backend.capability_v2.identity import authenticated_user_identity
from backend.capability_v2.contracts import ConsumerIdentity, IDENTITY_PATTERN, InvocationEnvelope
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.policies import GatewayPolicyError
from backend.platform_sdk.request_credentials import authenticated_transport_scope


class InvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, Any] = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)
    confirmation_token: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    expected_resource_version: str | None = Field(default=None, max_length=255)

    @model_validator(mode="before")
    @classmethod
    def reject_consumer_override(cls, value):
        if isinstance(value, dict) and (CONSUMER_IDENTITY_FIELDS.intersection(value) or
                isinstance(value.get("payload"), dict) and CONSUMER_IDENTITY_FIELDS.intersection(value["payload"])):
            raise HTTPException(status_code=400, detail={"code": "consumer_identity_override_forbidden"})
        return value


def _correlation_id(candidate: str | None, fallback: str) -> str:
    value = (candidate or "").strip()
    return value if re.fullmatch(IDENTITY_PATTERN, value) else fallback


def _web_identity(current_user: dict, principal) -> ConsumerIdentity:
    return authenticated_user_identity(current_user, principal)


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


async def _stream_response(result, gateway):
    """Claim only the stream returned by this same authenticated invocation.

    There is no public stream-id lookup route. Gateway keeps event, byte,
    lifetime, cancellation and invocation leases until this response closes.
    """
    stream_id = result.data['data']['stream_id']
    iterator, media_type = await gateway.claim_stream(stream_id)
    async def events():
        try:
            yield 'data: ' + json.dumps({'type':'capability_result','result':result.model_dump(mode='json')},ensure_ascii=False) + '\n\n'
            async for chunk in iterator:
                yield chunk
        finally:
            close = getattr(iterator,'aclose',None)
            if close:
                await close()
    return StreamingResponse(events(),media_type=media_type,headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


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
        envelope = InvocationEnvelope(
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
        )
        authorization = request.headers.get('Authorization', '')
        credential = authorization[7:] if authorization.lower().startswith('bearer ') else request.headers.get('X-AI00-Token', '')
        with authenticated_transport_scope(credential):
            result = await gateway.invoke(envelope)
        data = result.data.get('data') if isinstance(result.data,dict) else None
        if result.ok and isinstance(data,dict) and data.get('stream_id') and request.headers.get('Accept') == 'text/event-stream':
            return await _stream_response(result,gateway)
        return {"success": result.ok, "data": result.model_dump(mode="json")}

    return api


router = APIRouter()
router.include_router(_build_router("/api/v1/capabilities"))
