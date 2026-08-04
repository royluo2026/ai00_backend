"""REST adapters for the Capability Kernel (legacy and stable v1 routes)."""
from __future__ import annotations

from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.capabilities.init_next import CapabilityContext, CapabilityPermissionError, capability_registry
from backend.capabilities.registry_next import CapabilityConfirmationError
from backend.capabilities.confirmation_next import confirmation_manager
from backend.capabilities.validation_next import validate_payload
from backend.plugin_platform.service import authorize_plugin_invocation
from backend.routers.deps import build_profile, get_current_user


class InvokeRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)
    confirmation_token: str | None = None


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
    ):
        try:
            item = capability_registry.get(capability_id, body.version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "capability_not_found", "message": str(exc)}) from exc
        if item.spec.confirmation != "none" and not body.confirmation_token:
            raise HTTPException(status_code=409, detail={"code": "confirmation_required", "capability_id": item.spec.id, "version": item.spec.version})
        source = request.headers.get("X-AI00-Source", "web").strip().lower() or "web"
        plugin_identity = {}
        plugin_id = request.headers.get("X-AI00-Plugin-ID", "").strip()
        plugin_version = request.headers.get("X-AI00-Plugin-Version", "").strip()
        if source == "plugin" or plugin_id:
            if source not in {"plugin", "agent"}:
                raise HTTPException(status_code=400, detail={"code": "invalid_plugin_source", "message": "plugin identity is valid only for plugin or agent sources"})
            try:
                plugin_identity = authorize_plugin_invocation(current_user, plugin_id, plugin_version, item.spec.id)
            except (PermissionError, ValueError) as exc:
                raise HTTPException(status_code=403, detail={"code": "plugin_not_authorized", "message": str(exc)}) from exc
        request_id = request.headers.get("X-Request-ID") or f"cap_{uuid.uuid4().hex}"
        context = CapabilityContext(
            user_gid=current_user["gid"], team_gid=current_user.get("team_id") or None,
            source=source,
            request_id=request_id,
            confirmation_token=body.confirmation_token,
            permissions=tuple(build_profile(current_user).get("permissions", [])),
            agent_run_id=request.headers.get("X-AI00-Agent-Run-ID"),
            **plugin_identity,
        )
        try:
            result = await capability_registry.invoke(capability_id, body.payload, context, version=body.version)
        except CapabilityConfirmationError as exc:
            raise HTTPException(status_code=409, detail={"code": "confirmation_rejected", "message": str(exc)}) from exc
        except CapabilityPermissionError as exc:
            raise HTTPException(status_code=403, detail={"code": "permission_denied", "message": str(exc)}) from exc
        except (ValueError, LookupError) as exc:
            raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(exc)}) from exc
        return {"success": True, "data": result.model_dump(mode="json")}

    return api


router = APIRouter()
router.include_router(_build_router("/api/capabilities"))
router.include_router(_build_router("/api/v1/capabilities"))
