"""
backend/routers/projects.py
────────────────────────────
项目管理 API（projects + vehicle_models + project_members）

端点：
  GET  /api/projects                      → 项目列表（默认过滤 is_deleted=false）
  POST /api/projects                      → 创建项目
  GET  /api/projects/{gid}                → 项目详情
  PATCH /api/projects/{gid}               → 更新项目
  DELETE /api/projects/{gid}              → 软删除项目（is_deleted=true）
  GET  /api/projects/{gid}/members        → 项目成员列表
  POST /api/projects/{gid}/members        → 添加项目成员
  DELETE /api/projects/{gid}/members/{m}  → 移除项目成员
  GET  /api/projects/vehicle_models       → 车型列表
  POST /api/projects/vehicle_models       → 创建车型
"""
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.platform_sdk.access import build_access_scope
from backend.platform_sdk.auth import get_current_user, require_role, derive_org_role
from backend.platform_sdk.auth import get_authenticated_principal
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.craft_project_scope import equivalent_line_gids, line_titles, line_titles_for_project, project_bop_lines
from backend.platform_sdk.project_access import (
    add_project_member as add_project_access_member,
    can_manage_project,
    list_all_project_memberships,
    list_project_access_entries,
    remove_project_member as remove_project_access_member,
    replace_project_manager,
    replace_section_leads,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

_ANY_MEMBER = require_role("super_admin", "team_admin", "project_admin",
                           "rule_admin", "knowledge_admin", "member")
_PROJECT_WRITE = require_role("super_admin", "team_admin", "project_admin")
_ADMIN = require_role("super_admin", "team_admin")


def _row_to_project(row: dict) -> dict:
    """Legacy serialization shim retained for compatibility tests and callers."""
    result = dict(row)
    for field in ("created_at", "updated_at", "deleted_at", "archived_at"):
        if result.get(field) is not None:
            result[field] = str(result[field])
    return result


async def _invoke_project(request, user, principal, gateway, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="project.project.change.apply" if write else "project.project.read",
        payload={"operation": operation, "arguments": arguments}, current_user=user, principal=principal,
        request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else ""
        raise HTTPException(status_code={"not_found": 404, "forbidden": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


class CreateProjectBody(BaseModel):
    project_code: str                         # 项目代号，必填
    model_year: Optional[int] = None          # 年款，4位年份
    suffix: str = ""                          # 后缀（如 A、SOP、PRE 等）
    description: str = ""
    status: str = "preparing"
    vehicle_model_gid: Optional[str] = None
    team_id: Optional[str] = None
    jph: Optional[float] = None
    factory_gid: Optional[str] = None


class UpdateProjectBody(BaseModel):
    project_code: Optional[str] = None
    model_year: Optional[int] = None
    suffix: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    vehicle_model_gid: Optional[str] = None
    owner_gid: Optional[str] = None
    jph: Optional[float] = None
    is_archived: Optional[bool] = None
    factory_gid: Optional[str] = None


class AddMemberBody(BaseModel):
    user_gid: str
    project_role: str = "member"
    section_gid: Optional[str] = None


class LineGrantBody(BaseModel):
    user_gid: Optional[str] = None
    line_gid: Optional[str] = None


class CreateVehicleModelBody(BaseModel):
    name: str
    brand: str = ""
    platform: str = ""
    vehicle_type: str = ""
    team_id: Optional[str] = None


def _can_manage_project_lines(user: dict, project_gid: str) -> bool:
    """Base owns project membership and grant semantics."""
    org_role = user.get("org_role") or derive_org_role(user.get("system_role", "external"))
    return org_role == "super_admin" or can_manage_project(user["gid"], project_gid)


# ── 车型 ──────────────────────────────────────────────────────────

@router.get("/vehicle_models")
async def list_vehicle_models(request: Request, current_user: dict = Depends(_ANY_MEMBER), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "vehicle_models.list", {})


@router.post("/vehicle_models", status_code=201)
async def create_vehicle_model(body: CreateVehicleModelBody, request: Request, current_user: dict = Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "vehicle_models.create", body.model_dump(), write=True)


@router.patch("/vehicle_models/{gid}")
async def update_vehicle_model(gid: str, body: CreateVehicleModelBody, request: Request, current_user: dict = Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "vehicle_models.update", {"gid": gid, **body.model_dump()}, write=True)


@router.delete("/vehicle_models/{gid}")
async def delete_vehicle_model(gid: str, request: Request, current_user: dict = Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "vehicle_models.delete", {"gid": gid}, write=True)


# ── 项目 CRUD ─────────────────────────────────────────────────────

@router.get("")
async def list_projects(
    include_deleted: bool = Query(False),
    include_archived: bool = Query(False),
    request: Request = None,
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    access = build_access_scope(current_user)
    return await _invoke_project(request, current_user, principal, gateway, "projects.search", {"include_deleted": include_deleted, "include_archived": include_archived, "scope": access})


@router.post("", status_code=201)
async def create_project(body: CreateProjectBody, request: Request, current_user: dict = Depends(_PROJECT_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "projects.create", body.model_dump(), write=True)


@router.get("/members/matrix")
async def get_members_matrix(request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    """Compose the Auth membership projection with Craft-owned project/line names."""
    memberships = list_all_project_memberships()
    project_gids = sorted({row["project_gid"] for row in memberships if row.get("project_gid")})
    line_gids = sorted({row["scope_gid"] for row in memberships if row.get("scope_gid")})
    access = build_access_scope(current_user)
    project_result = await _invoke_project(request, current_user, principal, gateway, "projects.search", {"include_deleted": False, "include_archived": True, "scope": access})
    projects = {row["gid"]: row["name"] for row in project_result["data"] if row["gid"] in project_gids}
    sections = line_titles(line_gids)
    return {"success": True, "data": [
        {
            "user_gid": row["user_gid"], "name": row["name"],
            "email": row["email"], "avatar_url": row["avatar_url"],
            "project_gid": row["project_gid"], "project_name": projects[row["project_gid"]],
            "project_role": row["role"], "section_gid": row["scope_gid"],
            "section_title": sections.get(row["scope_gid"], ""),
        }
        for row in memberships if row.get("project_gid") in projects
    ]}


@router.get("/{gid}")
async def get_project(gid: str, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "projects.get", {"gid": gid})


@router.patch("/{gid}")
async def update_project(gid: str, body: UpdateProjectBody, request: Request, current_user: dict = Depends(_PROJECT_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "projects.update", {"gid": gid, "updates": body.model_dump(exclude_none=True)}, write=True)


@router.delete("/{gid}")
async def delete_project(gid: str, request: Request, current_user: dict = Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    """软删除：标记 is_deleted=TRUE，数据不实际删除。"""
    return await _invoke_project(request, current_user, principal, gateway, "projects.delete", {"gid": gid}, write=True)


# ── 项目成员 ──────────────────────────────────────────────────────

@router.get("/{gid}/members")
def list_project_members(gid: str, current_user: dict = Depends(get_current_user)):
    titles = line_titles_for_project(gid)
    rows = list_project_access_entries(gid, titles)
    seen = set()
    result = []
    for row in rows:
        key = (row["user_gid"], row.get("scope_gid") or "")
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "gid": row["gid"], "user_gid": row["user_gid"], "name": row["name"],
            "email": row["email"], "avatar_url": row["avatar_url"],
            "project_role": row["role"], "scope_gid": row.get("scope_gid"),
            "scope_type": row.get("scope_type") or "",
            "line_title": titles.get(row.get("scope_gid"), ""),
            "created_at": str(row["created_at"]),
        })
    return {"success": True, "data": result}


@router.post("/{gid}/members", status_code=201)
async def add_project_member(gid: str, body: AddMemberBody, request: Request, current_user: dict = Depends(_PROJECT_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _invoke_project(request, current_user, principal, gateway, "projects.get", {"gid": gid})
    try:
        member_gid = add_project_access_member(
            gid, body.user_gid, body.project_role, body.section_gid
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="该用户已是项目成员") from exc
    return {"success": True, "data": {"gid": member_gid}}


@router.delete("/{gid}/members/{member_gid}")
def remove_project_member(gid: str, member_gid: str, current_user: dict = Depends(_PROJECT_WRITE)):
    if not remove_project_access_member(gid, member_gid):
        raise HTTPException(status_code=404, detail="成员记录不存在")
    return {"success": True}


@router.get("/{gid}/bop-lines")
def get_project_bop_lines(gid: str, current_user: dict = Depends(get_current_user)):
    """返回项目所有活动 BOP 版本的线体，同名合并，附带所有相关 gid。"""
    return {"success": True, "data": project_bop_lines(gid)}


@router.put("/{gid}/line-assignment")
async def upsert_line_assignment(gid: str, body: LineGrantBody, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    """Replace project-manager or same-title line-lead assignments through Base access APIs."""
    if not _can_manage_project_lines(current_user, gid):
        raise HTTPException(status_code=403, detail="权限不足")
    await _invoke_project(request, current_user, principal, gateway, "projects.get", {"gid": gid})
    line_gids = equivalent_line_gids(gid, body.line_gid) if body.line_gid else []
    if body.line_gid and not line_gids:
        raise HTTPException(status_code=404, detail="线体不存在")
    if not body.line_gid:
        replace_project_manager(gid, body.user_gid)
    else:
        replace_section_leads(gid, line_gids, body.user_gid, current_user["gid"])
    return {"success": True}
