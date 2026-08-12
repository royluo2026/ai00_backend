"""Legacy follow HTTP adapter; Project owns follow behavior and SQL."""
from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.notifications import publish_notification
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility
from plugins.craft.craft_backend.public import get_follow_item_owner

router = APIRouter(prefix="/api/follows", tags=["follows"])


class CreateFollowBody(BaseModel):
    item_type: str
    item_gid: str
    item_title: str = ""
    notify_on: List[str] = ["status_change", "resolved"]


class PatchFollowBody(BaseModel):
    notify_on: List[str]


async def _invoke(request, user, principal, gateway, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="project.follow.change.apply" if write else "project.follow.read",
        payload={"operation": operation, "arguments": arguments}, current_user=user, principal=principal,
        request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else ""
        raise HTTPException({"not_found": 404, "already_exists": 409, "invalid_input": 400}.get(code, 422), result.error.model_dump(mode="json") if result.error else None)
    data = result.data["data"]
    notification = data.pop("notification", None) if isinstance(data, dict) else None
    if notification: publish_notification(notification["recipient_gid"], notification["event"], notification.get("item_type"), notification.get("item_gid"), "有人关注了你的内容")
    return data


@router.get("")
async def list_follows(request: Request, item_type: Optional[str] = Query(None), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "follows.list", {"item_type": item_type})


@router.get("/check")
async def check_follow(request: Request, item_type: str = Query(...), item_gid: str = Query(...), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "follows.check", {"item_type": item_type, "item_gid": item_gid})


@router.post("", status_code=201)
async def create_follow(body: CreateFollowBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    owner_gid = get_follow_item_owner(body.item_type, body.item_gid)
    return await _invoke(request, current_user, principal, gateway, "follows.create", {**body.model_dump(), "owner_gid": owner_gid}, write=True)


@router.patch("/{gid}")
async def patch_follow(gid: str, body: PatchFollowBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "follows.update", {"gid": gid, **body.model_dump()}, write=True)


@router.delete("/{gid}")
async def delete_follow(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "follows.delete", {"gid": gid}, write=True)
