"""Legacy workbench HTTP adapter; Project owns workbench behavior and SQL."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(prefix="/api/workbenches", tags=["workbenches"])


class CreateWbBody(BaseModel):
    name: str
    owner_type: str = "user"
    owner_gid: Optional[str] = None
    widgets: List[Dict[str, Any]] = []
    sort_order: int = 0


class UpdateWbBody(BaseModel):
    name: Optional[str] = None
    widgets: Optional[List[Dict[str, Any]]] = None
    sort_order: Optional[int] = None


async def _invoke(request, user, principal, gateway, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="project.workbench.change.apply" if write else "project.workbench.read",
        payload={"operation": operation, "arguments": arguments}, current_user=user, principal=principal,
        request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else ""
        raise HTTPException({"not_found": 404, "forbidden": 403, "invalid_input": 400}.get(code, 422), result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.get("")
async def list_workbenches(request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "workbenches.list", {})


@router.post("", status_code=201)
async def create_workbench(body: CreateWbBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "workbenches.create", body.model_dump(), write=True)


@router.patch("/{gid}")
async def update_workbench(gid: str, body: UpdateWbBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "workbenches.update", {"gid": gid, "updates": body.model_dump(exclude_none=True)}, write=True)


@router.delete("/{gid}")
async def delete_workbench(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "workbenches.delete", {"gid": gid}, write=True)


@router.get("/{gid}/override")
async def get_override(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "workbenches.overrides.get", {"gid": gid})


@router.put("/{gid}/override")
async def upsert_override(gid: str, request: Request, body: dict = Body(...), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "workbenches.overrides.upsert", {"gid": gid, "widgets": body.get("widgets", [])}, write=True)


@router.delete("/{gid}/override")
async def delete_override(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "workbenches.overrides.delete", {"gid": gid}, write=True)
