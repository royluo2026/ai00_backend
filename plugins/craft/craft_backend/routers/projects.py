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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.access import build_access_scope
from backend.platform_sdk.auth import get_current_user, require_role, get_user_grants, derive_org_role
from backend.platform_sdk.ids import next_gid
from backend.platform_sdk.project_access import (
    add_project_member as add_project_access_member,
    can_manage_project,
    get_user_profiles,
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


def _compute_name(project_code: str, model_year, suffix: str) -> str:
    """name 由 project_code + model_year + suffix 用 '-' 拼接，空部分跳过。"""
    parts = [p for p in [project_code, str(model_year) if model_year else None, suffix] if p]
    return "-".join(parts) or project_code


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


def _get_editable_line_gids(cur, user: dict, project_gid: str) -> set[str]:
    org_role = user.get("org_role") or derive_org_role(user.get("system_role", "external"))
    if org_role == "super_admin":
        cur.execute(
            "SELECT gid FROM workmanship_bop_bop_entries WHERE node_type = 'line_process' AND is_deleted = FALSE"
        )
        return {r["gid"] for r in cur.fetchall()}

    if _can_manage_project_lines(user, project_gid):
        cur.execute(
            "SELECT gid FROM workmanship_bop_bop_entries WHERE node_type = 'line_process' AND is_deleted = FALSE"
        )
        return {r["gid"] for r in cur.fetchall()}

    grants = get_user_grants(user["gid"])
    return {g["scope_gid"] for g in grants if g["grant_type"] == "section_lead" and g.get("scope_gid")}
def _row_to_project(r):
    return {
        "gid":               r["gid"],
        "name":              r["name"],
        "project_code":      r["project_code"] or "",
        "model_year":        r["model_year"],
        "suffix":            r["suffix"] or "",
        "description":       r["description"] or "",
        "status":            r["status"],
        "vehicle_model_gid": r["vehicle_model_gid"],
        "factory_gid":       r.get("factory_gid"),
        "team_id":           r["team_id"],
        "owner_gid":         r["owner_gid"],
        "owner_name":        r.get("owner_name") or "",
        "share_scope":       r["share_scope"],
        "jph":               r["jph"],
        "is_deleted":        r["is_deleted"],
        "is_archived":       r["is_archived"],
        "deleted_at":        str(r["deleted_at"]) if r["deleted_at"] else None,
        "archived_at":       str(r["archived_at"]) if r["archived_at"] else None,
        "created_at":        str(r["created_at"]),
        "updated_at":        str(r["updated_at"]),
    }


# ── 车型 ──────────────────────────────────────────────────────────

@router.get("/vehicle_models")
def list_vehicle_models(current_user: dict = Depends(_ANY_MEMBER)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, name, brand, platform, vehicle_type, created_at FROM workmanship_proj_vehicle_models ORDER BY created_at DESC")
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "name": r["name"], "brand": r["brand"],
         "platform": r["platform"], "vehicle_type": r.get("vehicle_type") or "",
         "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.post("/vehicle_models", status_code=201)
def create_vehicle_model(body: CreateVehicleModelBody, current_user: dict = Depends(_ADMIN)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_proj_vehicle_models (gid, name, brand, platform, vehicle_type, team_id, meta) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (gid, body.name, body.brand, body.platform, body.vehicle_type, body.team_id or current_user.get("team_id"), '{}')
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "name": body.name}}


@router.patch("/vehicle_models/{gid}")
def update_vehicle_model(gid: str, body: CreateVehicleModelBody, current_user: dict = Depends(_ADMIN)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_vehicle_models SET name=%s, brand=%s, platform=%s, vehicle_type=%s WHERE gid=%s",
                (body.name, body.brand, body.platform, body.vehicle_type, gid)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="车型不存在")
        conn.commit()
    return {"success": True}


@router.delete("/vehicle_models/{gid}")
def delete_vehicle_model(gid: str, current_user: dict = Depends(_ADMIN)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_proj_vehicle_models WHERE gid=%s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="车型不存在")
        conn.commit()
    return {"success": True}


# ── 项目 CRUD ─────────────────────────────────────────────────────

@router.get("")
def list_projects(
    include_deleted: bool = Query(False),
    include_archived: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    access = build_access_scope(current_user)
    conditions = []
    params = []
    if not access["is_admin"]:
        visible = ["p.share_scope = 'global'", "p.owner_gid = %s"]
        params.append(access["user_gid"])
        if access["team_gids"]:
            placeholders = ",".join(["%s"] * len(access["team_gids"]))
            visible.append(f"(p.share_scope = 'team' AND p.team_id IN ({placeholders}))")
            params.extend(access["team_gids"])
        if access["project_gids"]:
            placeholders = ",".join(["%s"] * len(access["project_gids"]))
            visible.append(f"(p.share_scope IN ('team','project') AND p.gid IN ({placeholders}))")
            params.extend(access["project_gids"])
        conditions.append("(" + " OR ".join(visible) + ")")
    if not include_deleted:
        conditions.append("p.is_deleted = FALSE")
    if not include_archived:
        conditions.append("p.is_archived = FALSE")
    where = " AND ".join(conditions) or "1=1"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT p.gid, p.name, p.project_code, p.model_year, p.suffix, "
                f"p.description, p.status, p.vehicle_model_gid, p.factory_gid, "
                f"p.team_id, p.owner_gid, p.share_scope, p.jph, "
                f"p.is_deleted, p.is_archived, p.deleted_at, p.archived_at, "
                f"p.created_at, p.updated_at FROM workmanship_proj_projects p "
                f"WHERE {where} ORDER BY p.updated_at DESC",
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
    profiles = get_user_profiles(row["owner_gid"] for row in rows)
    for row in rows:
        row["owner_name"] = profiles.get(str(row["owner_gid"]), {}).get("name", "")
    return {"success": True, "data": [_row_to_project(row) for row in rows]}


@router.post("", status_code=201)
def create_project(body: CreateProjectBody, current_user: dict = Depends(_PROJECT_WRITE)):
    if not body.project_code.strip():
        raise HTTPException(status_code=400, detail="project_code 不能为空")
    if body.model_year is not None and not (2000 <= body.model_year <= 2099):
        raise HTTPException(status_code=400, detail="model_year 须为 2000–2099 的年份")
    gid = str(next_gid())
    name = _compute_name(body.project_code.strip(), body.model_year, body.suffix.strip())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_proj_projects "
                 "(gid, name, project_code, model_year, suffix, description, status, "
                 " vehicle_model_gid, team_id, owner_gid, jph, factory_gid, share_scope, project_type, meta) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, name, body.project_code.strip(), body.model_year,
                  body.suffix.strip(), body.description, body.status,
                 body.vehicle_model_gid,
                 body.team_id or current_user.get("team_id"), current_user["gid"],
                 body.jph, body.factory_gid, 'team', 'active', '{}')
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "name": name}}


@router.get("/members/matrix")
def get_members_matrix(current_user: dict = Depends(get_current_user)):
    """Compose the Auth membership projection with Craft-owned project/line names."""
    memberships = list_all_project_memberships()
    project_gids = sorted({row["project_gid"] for row in memberships if row.get("project_gid")})
    line_gids = sorted({row["scope_gid"] for row in memberships if row.get("scope_gid")})
    projects = {}
    sections = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            if project_gids:
                placeholders = ",".join(["%s"] * len(project_gids))
                cur.execute(
                    f"SELECT gid, name FROM workmanship_proj_projects "
                    f"WHERE is_deleted=FALSE AND gid IN ({placeholders})",
                    project_gids,
                )
                projects = {row["gid"]: row["name"] for row in cur.fetchall()}
            if line_gids:
                placeholders = ",".join(["%s"] * len(line_gids))
                cur.execute(
                    f"SELECT gid, title FROM workmanship_bop_bop_entries WHERE gid IN ({placeholders})",
                    line_gids,
                )
                sections = {row["gid"]: row["title"] for row in cur.fetchall()}
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
def get_project(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, project_code, model_year, suffix, description, status, "
                "vehicle_model_gid, factory_gid, team_id, owner_gid, share_scope, jph, "
                "is_deleted, is_archived, deleted_at, archived_at, meta, created_at, updated_at "
                "FROM workmanship_proj_projects WHERE gid = %s",
                (gid,)
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    result = _row_to_project(row)
    result["meta"] = row["meta"]
    return {"success": True, "data": result}


@router.patch("/{gid}")
def update_project(gid: str, body: UpdateProjectBody, current_user: dict = Depends(_PROJECT_WRITE)):
    if body.model_year is not None and not (2000 <= body.model_year <= 2099):
        raise HTTPException(status_code=400, detail="model_year 须为 2000–2099 的年份")

    set_parts = []
    vals = []

    # 收集三个派生 name 的字段变更
    name_fields_changed = any(v is not None for v in [body.project_code, body.model_year, body.suffix])

    if body.project_code is not None:
        set_parts.append("project_code = %s"); vals.append(body.project_code.strip())
    if body.model_year is not None:
        set_parts.append("model_year = %s"); vals.append(body.model_year)
    if body.suffix is not None:
        set_parts.append("suffix = %s"); vals.append(body.suffix.strip())
    if body.description is not None:
        set_parts.append("description = %s"); vals.append(body.description)
    if body.status is not None:
        set_parts.append("status = %s"); vals.append(body.status)
    if body.vehicle_model_gid is not None:
        set_parts.append("vehicle_model_gid = %s"); vals.append(body.vehicle_model_gid)
    if body.owner_gid is not None:
        set_parts.append("owner_gid = %s"); vals.append(body.owner_gid)
    if body.jph is not None:
        set_parts.append("jph = %s"); vals.append(body.jph)
    if body.factory_gid is not None:
        set_parts.append("factory_gid = %s"); vals.append(body.factory_gid)
    if body.is_archived is not None:
        set_parts.append("is_archived = %s"); vals.append(body.is_archived)
        if body.is_archived:
            set_parts.append("archived_at = NOW()")
        else:
            set_parts.append("archived_at = NULL")

    if not set_parts:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    # 如果三个 name 派生字段任意变更，重新计算 name
    if name_fields_changed:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT project_code, model_year, suffix FROM workmanship_proj_projects WHERE gid = %s",
                    (gid,)
                )
                cur_row = cur.fetchone()
        if not cur_row:
            raise HTTPException(status_code=404, detail="项目不存在或已删除")
        new_code  = body.project_code.strip() if body.project_code is not None else (cur_row["project_code"] or "")
        new_year  = body.model_year  if body.model_year  is not None else cur_row["model_year"]
        new_suf   = body.suffix.strip() if body.suffix is not None else (cur_row["suffix"] or "")
        new_name  = _compute_name(new_code, new_year, new_suf)
        set_parts.append("name = %s"); vals.append(new_name)

    set_parts.append("updated_at = NOW()")
    vals.append(gid)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_proj_projects SET {', '.join(set_parts)} WHERE gid = %s AND is_deleted = FALSE", vals)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="项目不存在或已删除")
        conn.commit()
    return {"success": True}


@router.delete("/{gid}")
def delete_project(gid: str, current_user: dict = Depends(_ADMIN)):
    """软删除：标记 is_deleted=TRUE，数据不实际删除。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_projects SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW() "
                "WHERE gid = %s AND is_deleted = FALSE",
                (gid,)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="项目不存在或已删除")
        conn.commit()
    return {"success": True}


# ── 项目成员 ──────────────────────────────────────────────────────

@router.get("/{gid}/members")
def list_project_members(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT e.gid, e.title FROM workmanship_bop_bop_entries e "
                "JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid "
                "WHERE v.project_gid=%s AND v.archived_at IS NULL "
                "AND e.node_type='line_process' AND e.is_deleted=FALSE",
                (gid,),
            )
            line_titles = {row["gid"]: row["title"] or "" for row in cur.fetchall()}
    rows = list_project_access_entries(gid, line_titles)
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
            "line_title": line_titles.get(row.get("scope_gid"), ""),
            "created_at": str(row["created_at"]),
        })
    return {"success": True, "data": result}


@router.post("/{gid}/members", status_code=201)
def add_project_member(gid: str, body: AddMemberBody, current_user: dict = Depends(_PROJECT_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_proj_projects WHERE gid=%s AND is_deleted=FALSE", (gid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="项目不存在")
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
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, title, sort_order FROM workmanship_bop_bop_entries "
                "WHERE version_gid IN ("
                "  SELECT gid FROM workmanship_bop_bop_versions "
                "  WHERE project_gid = %s AND archived_at IS NULL"
                ") AND node_type = 'line_process' AND is_deleted = FALSE "
                "ORDER BY sort_order, title",
                (gid,)
            )
            rows = cur.fetchall()
    # 按 title 分组：收集所有 gid
    by_title = {}
    for r in rows:
        title = r["title"] or ""
        if title not in by_title:
            by_title[title] = {"gid": r["gid"], "title": r["title"] or "（未命名线体）",
                               "seq_no": r["sort_order"], "all_gids": []}
        by_title[title]["all_gids"].append(r["gid"])
    return {"success": True, "data": list(by_title.values())}


@router.put("/{gid}/line-assignment")
def upsert_line_assignment(gid: str, body: LineGrantBody, current_user: dict = Depends(get_current_user)):
    """Replace project-manager or same-title line-lead assignments through Base access APIs."""
    if not _can_manage_project_lines(current_user, gid):
        raise HTTPException(status_code=403, detail="权限不足")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_proj_projects WHERE gid=%s AND is_deleted=FALSE", (gid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="项目不存在")
            if not body.line_gid:
                line_gids = []
            else:
                cur.execute(
                    "SELECT title FROM workmanship_bop_bop_entries "
                    "WHERE gid=%s AND node_type='line_process' AND is_deleted=FALSE",
                    (body.line_gid,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="线体不存在")
                cur.execute(
                    "SELECT e.gid FROM workmanship_bop_bop_entries e "
                    "JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid "
                    "WHERE v.project_gid=%s AND v.archived_at IS NULL "
                    "AND e.node_type='line_process' AND e.is_deleted=FALSE AND e.title=%s",
                    (gid, row["title"]),
                )
                line_gids = [item["gid"] for item in cur.fetchall()]
                if not line_gids:
                    raise HTTPException(status_code=404, detail="线体不存在")
    if not body.line_gid:
        replace_project_manager(gid, body.user_gid)
    else:
        replace_section_leads(gid, line_gids, body.user_gid, current_user["gid"])
    return {"success": True}
