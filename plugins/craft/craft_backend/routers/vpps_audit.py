"""REST compatibility adapters for governed Craft VPPS operation auditing."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user, require_role
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/vpps-operations", tags=["vpps_audit"])
_READ = require_role("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "project_admin", "member")


class IgnoreRow(BaseModel):
    pbom_row_gid: str
    original_vpps_desc: Optional[str] = None
    notes: Optional[str] = None


class BulkIgnoreRule4Body(BaseModel):
    pbom_version_gid: str
    rows: list[IgnoreRow]
    actor_gid: Optional[str] = None
    actor_name: Optional[str] = None


class RevertBody(BaseModel):
    reverted_by_gid: Optional[str] = None
    reverted_by_name: Optional[str] = None


async def _invoke_vpps_audit(request, current_user, principal, gateway, capability_id, operation, *, pbom_version_gid=None, operation_type=None, gid=None, rows=None, actor_gid=None, actor_name=None):
    request_id = request.headers.get("X-Request-ID") or f"craft_vpps_audit_legacy_{next_gid()}"
    payload = {"operation": operation}
    for key, value in (("pbom_version_gid", pbom_version_gid), ("operation_type", operation_type), ("gid", gid), ("rows", rows), ("actor_gid", actor_gid), ("actor_name", actor_name)):
        if value is not None:
            payload[key] = value
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload=payload, current_user=current_user,
        principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    data = result.data
    if operation == "list":
        return {"success": data["success"], "data": data["items"]}
    return data


@router.post("/rule4-bulk-ignore", dependencies=[Depends(_WRITE)])
async def rule4_bulk_ignore(body: BulkIgnoreRule4Body, request: Request, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_vpps_audit(request, user, principal, gateway, "craft.vpps_audit.change.apply", "rule4_bulk_ignore", pbom_version_gid=body.pbom_version_gid, rows=[row.model_dump() for row in body.rows], actor_gid=body.actor_gid or user.get("gid"), actor_name=body.actor_name or user.get("name", ""))


@router.get("", dependencies=[Depends(_READ)])
async def list_operations(pbom_version_gid: str, operation_type: Optional[str] = None, request: Request = None, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_vpps_audit(request, user, principal, gateway, "craft.vpps_audit.read", "list", pbom_version_gid=pbom_version_gid, operation_type=operation_type)


@router.get("/rule4-ignores", dependencies=[Depends(_READ)])
async def get_rule4_ignores(pbom_version_gid: str, request: Request, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_vpps_audit(request, user, principal, gateway, "craft.vpps_audit.read", "rule4_ignores", pbom_version_gid=pbom_version_gid)


@router.post("/{gid}/revert", dependencies=[Depends(_WRITE)])
async def revert_operation(gid: str, body: RevertBody, request: Request, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_vpps_audit(request, user, principal, gateway, "craft.vpps_audit.change.apply", "revert", gid=gid, actor_gid=body.reverted_by_gid or user.get("gid"), actor_name=body.reverted_by_name or user.get("name", ""))
