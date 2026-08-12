"""Legacy task-template HTTP adapter; Project owns all behavior and SQL."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, require_role
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(prefix="/api/task-templates", tags=["task_templates"])
_READ = require_role("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "knowledge_admin")


class CreateTemplateBody(BaseModel):
    name: str
    description: str = ""
    scope: str = "system"


class UpdateTemplateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[str] = None
    is_active: Optional[bool] = None


class CreateItemBody(BaseModel):
    title_pattern: str
    description: str = ""
    priority: str = "normal"
    assignee_role: Optional[str] = None
    due_offset_days: Optional[int] = None
    share_scope: str = "team"
    sort_order: int = 0


class UpdateItemBody(BaseModel):
    title_pattern: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    assignee_role: Optional[str] = None
    due_offset_days: Optional[int] = None
    share_scope: Optional[str] = None
    sort_order: Optional[int] = None


class InstantiateBody(BaseModel):
    project_gid: str
    start_date: str
    assignee_map: dict = {}
    title_vars: dict = {}
    owner_user_gid: Optional[str] = None


async def _invoke(request, user, principal, gateway, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="project.task_template.change.apply" if write else "project.task_template.read",
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
async def list_templates(request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "task_templates.list", {})


@router.post("", status_code=201)
async def create_template(body: CreateTemplateBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "task_templates.create", body.model_dump(), write=True)


@router.get("/{gid}")
async def get_template(gid: str, request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "task_templates.get", {"gid": gid})


@router.patch("/{gid}")
async def update_template(gid: str, body: UpdateTemplateBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "task_templates.update", {"gid": gid, "updates": body.model_dump(exclude_none=True)}, write=True)


@router.delete("/{gid}", status_code=204)
async def delete_template(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _invoke(request, current_user, principal, gateway, "task_templates.delete", {"gid": gid}, write=True)


@router.post("/{template_gid}/items", status_code=201)
async def add_item(template_gid: str, body: CreateItemBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "task_templates.items.create", {"template_gid": template_gid, **body.model_dump()}, write=True)


@router.patch("/items/{item_gid}")
async def update_item(item_gid: str, body: UpdateItemBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "task_templates.items.update", {"item_gid": item_gid, "updates": body.model_dump(exclude_none=True)}, write=True)


@router.delete("/items/{item_gid}", status_code=204)
async def delete_item(item_gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _invoke(request, current_user, principal, gateway, "task_templates.items.delete", {"item_gid": item_gid}, write=True)


@router.post("/{gid}/instantiate", status_code=201)
async def instantiate(gid: str, body: InstantiateBody, request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "task_templates.instantiate", {"gid": gid, **body.model_dump()}, write=True)
