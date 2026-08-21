"""REST compatibility adapters for governed Craft rule evaluation."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.ids import next_gid

router = APIRouter(tags=["rule-engine"])


class CheckBody(BaseModel):
    rule_gid: str
    context: dict[str, Any] = {}


async def _invoke_rule_engine(request, current_user, principal, gateway, operation, *, rule_gid=None, context=None, version_gid=None, dry_run=True):
    request_id = request.headers.get("X-Request-ID") or f"craft_rule_engine_legacy_{next_gid()}"
    payload = {"operation": operation}
    if rule_gid:
        payload["rule_gid"] = rule_gid
    if context is not None:
        payload["context"] = context
    if version_gid:
        payload["version_gid"] = version_gid
    payload["dry_run"] = dry_run
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.rule.engine.evaluate", payload=payload, current_user=current_user,
        principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.post("/api/rule-engine/check")
async def check_single_rule(body: CheckBody, request: Request, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_rule_engine(request, user, principal, gateway, "check", rule_gid=body.rule_gid, context=body.context)


@router.post("/api/rule-engine/audit/bop-version/{version_gid}")
async def audit_bop_version(version_gid: str, dry_run: bool = Query(True, description="True=只返回结果，False=同时创建 Issue"), request: Request = None, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_rule_engine(request, user, principal, gateway, "audit", version_gid=version_gid, dry_run=dry_run)
