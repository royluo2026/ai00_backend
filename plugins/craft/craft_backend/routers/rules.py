"""REST compatibility adapters for governed Craft rule-library CRUD."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.ids import next_gid

router = APIRouter(tags=["rules"])


class RuleBody(BaseModel):
    code: str = ""
    name: str
    rule_type: str = "process"
    enforcement_level: str = "advisory"
    status: str = "draft"
    share_scope: str = "team"
    list_gid: Optional[str] = None
    context_class_gid: Optional[str] = None
    rule_definition: dict = {}


async def _invoke_rule_library(request, current_user, principal, gateway, capability_id, operation, *, gid=None, record=None, status=None, list_gid=None, q=None, limit=None):
    request_id = request.headers.get("X-Request-ID") or f"craft_rule_library_legacy_{next_gid()}"
    payload = {"operation": operation}
    for key, value in (("gid", gid), ("record", record), ("status", status), ("list_gid", list_gid), ("q", q), ("limit", limit)):
        if value is not None:
            payload[key] = value
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload=payload, current_user=current_user,
        principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.get("/api/rules")
async def list_rules(status: Optional[str] = Query(None), list_gid: Optional[str] = Query(None), q: Optional[str] = Query(None), limit: Optional[int] = Query(None), request: Request = None, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_rule_library(request, current_user, principal, gateway, "craft.rule.library.read", "list", status=status, list_gid=list_gid, q=q, limit=limit)


@router.post("/api/rules", status_code=201)
async def create_rule(body: RuleBody, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_rule_library(request, current_user, principal, gateway, "craft.rule.library.change.apply", "create", record=body.model_dump())


@router.get("/api/rules/{gid}")
async def get_rule(gid: str, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_rule_library(request, current_user, principal, gateway, "craft.rule.library.read", "get", gid=gid)


@router.patch("/api/rules/{gid}")
async def update_rule(gid: str, body: dict, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_rule_library(request, current_user, principal, gateway, "craft.rule.library.change.apply", "update", gid=gid, record=body)


@router.delete("/api/rules/{gid}")
async def delete_rule(gid: str, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_rule_library(request, current_user, principal, gateway, "craft.rule.library.change.apply", "delete", gid=gid)
