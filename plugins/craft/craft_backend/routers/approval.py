"""Legacy approval HTTP adapter; Project owns approval behavior and SQL."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.access import build_access_scope
from backend.platform_sdk.auth import get_authenticated_principal, require_role
from backend.platform_sdk.identity import find_active_user_by_role
from backend.platform_sdk.notifications import publish_notification
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(prefix="/api/approval", tags=["approval"])
_SUBMIT = require_role("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member")
_APPROVE = require_role("super_admin", "team_admin", "project_admin")


class CreateOrderBody(BaseModel):
    title: str
    order_type: str = "general"
    project_gid: Optional[str] = None
    reviewer_gid: Optional[str] = None
    source_ref: Optional[str] = None
    content: dict = {}


class ScopeUpgradeBody(BaseModel):
    item_type: str
    item_gid: str
    item_title: str
    current_scope: str
    target_scope: str
    reason: str = ""


class OpinionBody(BaseModel):
    comment: str = ""


async def _invoke(request, user, principal, gateway, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="project.approval.change.apply" if write else "project.approval.read",
        payload={"operation": operation, "arguments": arguments}, current_user=user, principal=principal,
        request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else ""
        raise HTTPException({"not_found": 404, "forbidden": 403, "invalid_input": 400, "invalid_state": 400}.get(code, 422), result.error.model_dump(mode="json") if result.error else None)
    data = result.data["data"]
    notification = data.pop("notification", None) if isinstance(data, dict) else None
    if notification:
        publish_notification(notification["recipient_gid"], notification["event"], notification.get("item_type"), notification.get("item_gid"), "审批状态已更新")
    return data


@router.get("/orders")
async def list_orders(request: Request, status: Optional[str] = Query(None), project_gid: Optional[str] = Query(None), current_user=Depends(_SUBMIT), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "approval.orders.search", {"status": status, "project_gid": project_gid, "scope": build_access_scope(current_user)})


@router.post("/orders", status_code=201)
async def create_order(body: CreateOrderBody, request: Request, current_user=Depends(_SUBMIT), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "approval.orders.create", body.model_dump(), write=True)


@router.get("/orders/{gid}")
async def get_order(gid: str, request: Request, current_user=Depends(_SUBMIT), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "approval.orders.get", {"gid": gid})


async def _transition(gid, operation, comment, request, user, principal, gateway):
    return await _invoke(request, user, principal, gateway, operation, {"gid": gid, "comment": comment}, write=True)


@router.post("/orders/{gid}/start")
async def start_review(gid: str, request: Request, current_user=Depends(_SUBMIT), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _transition(gid, "approval.orders.start", "", request, current_user, principal, gateway)


@router.post("/orders/{gid}/approve")
async def approve_order(gid: str, body: OpinionBody, request: Request, current_user=Depends(_APPROVE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _transition(gid, "approval.orders.approve", body.comment, request, current_user, principal, gateway)


@router.post("/orders/{gid}/reject")
async def reject_order(gid: str, body: OpinionBody, request: Request, current_user=Depends(_APPROVE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _transition(gid, "approval.orders.reject", body.comment, request, current_user, principal, gateway)


@router.post("/orders/{gid}/withdraw")
async def withdraw_order(gid: str, request: Request, current_user=Depends(_SUBMIT), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _transition(gid, "approval.orders.withdraw", "", request, current_user, principal, gateway)


@router.post("/orders/scope_upgrade", status_code=201)
async def create_scope_upgrade_order(body: ScopeUpgradeBody, request: Request, current_user=Depends(_SUBMIT), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    reviewer_role = {"project": "project_admin", "team": "team_admin", "global": "super_admin"}.get(body.target_scope)
    reviewer_gid = find_active_user_by_role(reviewer_role, current_user.get("team_id")) if reviewer_role else None
    return await _invoke(request, current_user, principal, gateway, "approval.scope_upgrade.create", {**body.model_dump(), "reviewer_gid": reviewer_gid}, write=True)
