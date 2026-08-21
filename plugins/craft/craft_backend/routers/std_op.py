"""REST compatibility adapters for Craft's governed standard-operation APIs."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, require_role
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/std_op", tags=["std_op"])
_READ = require_role("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "knowledge_admin")


class CreateOpBody(BaseModel):
    code: str
    name: str
    standard_time: float = 0
    importance: Optional[str] = None
    description: str = ""
    level: str = ""
    vpps_attr: str = ""
    vpps: Optional[str] = None
    vpps_desc: str = ""
    torque_importance: str = ""
    vehicle_model: str = ""
    parent_vpps: str = ""
    steps: list = []
    required_tools: list = []
    parameters: dict = {}


class UpdateOpBody(BaseModel):
    name: Optional[str] = None
    standard_time: Optional[float] = None
    importance: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    vpps_attr: Optional[str] = None
    vpps: Optional[str] = None
    vpps_desc: Optional[str] = None
    torque_importance: Optional[str] = None
    vehicle_model: Optional[str] = None
    parent_vpps: Optional[str] = None
    steps: Optional[list] = None
    required_tools: Optional[list] = None
    parameters: Optional[dict] = None


class CloneToPostBody(BaseModel):
    post_gid: str
    seq_no: int = 0


async def _invoke_standard_operation(request, current_user, principal, gateway, capability_id, operation, *, gid=None, status=None, record=None):
    request_id = request.headers.get("X-Request-ID") or f"craft_std_op_legacy_{next_gid()}"
    payload = {"operation": operation}
    if gid:
        payload["gid"] = gid
    if status:
        payload["status"] = status
    if record is not None:
        payload["record"] = record
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload=payload, current_user=current_user,
        principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.get("/operations")
async def list_operations(status: Optional[str] = Query(None), request: Request = None, current_user: dict = Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_standard_operation(request, current_user, principal, gateway, "craft.standard_operation.read", "list", status=status)


@router.post("/operations", status_code=201)
async def create_operation(body: CreateOpBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_standard_operation(request, current_user, principal, gateway, "craft.standard_operation.change.apply", "create", record=body.model_dump())


@router.get("/operations/{gid}")
async def get_operation(gid: str, request: Request, current_user: dict = Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_standard_operation(request, current_user, principal, gateway, "craft.standard_operation.read", "get", gid=gid)


@router.patch("/operations/{gid}")
async def update_operation(gid: str, body: UpdateOpBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_standard_operation(request, current_user, principal, gateway, "craft.standard_operation.change.apply", "update", gid=gid, record=body.model_dump(exclude_none=True))


@router.delete("/operations/{gid}")
async def delete_operation(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_standard_operation(request, current_user, principal, gateway, "craft.standard_operation.change.apply", "delete", gid=gid)


@router.post("/operations/{gid}/publish")
async def publish_operation(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_standard_operation(request, current_user, principal, gateway, "craft.standard_operation.change.apply", "publish", gid=gid)


@router.post("/operations/{gid}/deprecate")
async def deprecate_operation(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_standard_operation(request, current_user, principal, gateway, "craft.standard_operation.change.apply", "deprecate", gid=gid)


@router.post("/operations/{gid}/clone-to-post", status_code=201)
async def clone_to_post(gid: str, body: CloneToPostBody, current_user: dict = Depends(_READ)):
    raise HTTPException(status_code=410, detail="V1 bop_posts/bop_operations 已废弃，请使用新 BOP entry API")
