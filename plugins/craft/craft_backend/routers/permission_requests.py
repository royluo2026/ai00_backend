"""Temporary Gateway adapters for Project Management permission requests."""
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.identity import get_user_summaries
from backend.platform_sdk.notifications import publish_notification
from plugins.project_management.project_management_backend.api.compatibility import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(tags=["permission_requests"])
class PermReqBody(BaseModel):
    target_type: str
    target_gid: str
    want_permission: str = "read"
    message: str = ""
class RejectBody(BaseModel):
    message: str = ""

async def _invoke(request, user, principal, gateway, capability_id, operation, arguments):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    write = capability_id.endswith("change.apply")
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload={"operation": operation, "arguments": arguments}, current_user=user,
        principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_failed"
        raise HTTPException(404 if code == "not_found" else 400 if code == "already_decided" else 422, result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]

@router.post("/api/permission-requests", status_code=status.HTTP_201_CREATED)
async def create_permission_request(body: PermReqBody, request: Request, user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, user, principal, gateway, "project.permission_request.change.apply", "permission_requests.create", body.model_dump())

@router.get("/api/permission-requests")
async def list_permission_requests(request: Request, target_gid: Optional[str] = Query(None), status_filter: Optional[str] = Query(None, alias="status"), user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, user, principal, gateway, "project.permission_request.read", "permission_requests.list", {"target_gid": target_gid, "status": status_filter})
    users = get_user_summaries(row.get("requester_gid") for row in data["requests"])
    for row in data["requests"]:
        summary = users.get(str(row.get("requester_gid")), {})
        row["requester_name"], row["requester_avatar"] = summary.get("name"), summary.get("avatar_url")
    return data

async def _decide(gid, decision, request, user, principal, gateway):
    data = await _invoke(request, user, principal, gateway, "project.permission_request.change.apply", f"permission_requests.{decision}", {"gid": gid})
    notice = data.pop("notification")
    publish_notification(notice["recipient_gid"], notice["event"], notice["target_type"], notice["target_gid"], f"您申请访问 {notice['target_gid']} 的权限已{'批准' if decision == 'approve' else '被拒绝'}")
    return data

@router.post("/api/permission-requests/{gid}/approve")
async def approve_permission_request(gid: str, request: Request, user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _decide(gid, "approve", request, user, principal, gateway)

@router.post("/api/permission-requests/{gid}/reject")
async def reject_permission_request(gid: str, body: RejectBody, request: Request, user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _decide(gid, "reject", request, user, principal, gateway)
