"""Notification HTTP composition: Project messages plus Base preferences."""
from __future__ import annotations

from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.notification_preferences import DEFAULTS, get_notification_preferences, update_notification_preferences
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


async def _invoke(request, user, principal, gateway, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="project.notification.change.apply" if write else "project.notification.read",
        payload={"operation": operation, "arguments": arguments}, current_user=user, principal=principal,
        request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok: raise HTTPException(422, result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.get("")
async def list_notifications(request: Request, unread_only: bool = Query(False), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    try: return await _invoke(request, current_user, principal, gateway, "notifications.list", {"unread_only": unread_only})
    except Exception: return {"success": True, "data": []}


@router.get("/unread_count")
async def unread_count(request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    try: return await _invoke(request, current_user, principal, gateway, "notifications.unread_count", {})
    except Exception: return {"success": True, "data": {"count": 0}}


@router.get("/prefs")
def get_prefs(current_user=Depends(get_current_user)):
    try: return {"success": True, "data": get_notification_preferences(current_user["gid"])}
    except Exception: return {"success": True, "data": dict(DEFAULTS)}


@router.patch("/prefs")
def update_prefs(body: dict, current_user=Depends(get_current_user)):
    try: return {"success": True, "data": update_notification_preferences(current_user["gid"], body)}
    except Exception as exc: return {"success": False, "msg": str(exc)}


@router.patch("/read_all")
async def read_all(request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    try: return await _invoke(request, current_user, principal, gateway, "notifications.mark_all_read", {}, write=True)
    except Exception: return {"success": True}


@router.patch("/{gid}/read")
async def mark_read(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    try: return await _invoke(request, current_user, principal, gateway, "notifications.mark_read", {"gid": gid}, write=True)
    except Exception: return {"success": True}
