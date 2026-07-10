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

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, require_role, scope_visible_clause
from backend.utils.gid import next_gid

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


class LineAssignmentBody(BaseModel):
    slot: str                        # 'project_owner' | 'section_lead'
    section_gid: Optional[str] = None
    user_gid: Optional[str] = None   # None = clear the slot


class CreateVehicleModelBody(BaseModel):
    name: str
    brand: str = ""
    platform: str = ""
    vehicle_type: str = ""
    team_id: Optional[str] = None


def _row_to_project(r: dict) -> dict:
    """将 RealDictRow 序列化为前端需要的字典（统一处理时间戳/None）。"""
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
                "INSERT INTO workmanship_proj_vehicle_models (gid, name, brand, platform, vehicle_type, team_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (gid, body.name, body.brand, body.platform, body.vehicle_type, body.team_id or current_user.get("team_id"))
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
    scope_sql, scope_params = scope_visible_clause(current_user, owner_col="p.owner_gid", team_col="p.team_id")
    conditions = [scope_sql]
    params = list(scope_params)
    if not include_deleted:
        conditions.append("p.is_deleted = FALSE")
    if not include_archived:
        conditions.append("p.is_archived = FALSE")
    where = " AND ".join(conditions)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT p.gid, p.name, p.project_code, p.model_year, p.suffix, "
                f"p.description, p.status, p.vehicle_model_gid, p.factory_gid, "
                f"p.team_id, p.owner_gid, p.share_scope, p.jph, "
                f"p.is_deleted, p.is_archived, p.deleted_at, p.archived_at, "
                f"p.created_at, p.updated_at, "
                f"u.name AS owner_name "
                f"FROM workmanship_proj_projects p LEFT JOIN workmanship_auth_users u ON p.owner_gid = u.gid "
                f"WHERE {where} ORDER BY p.updated_at DESC",
                params
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_row_to_project(r) for r in rows]}


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
                 " vehicle_model_gid, team_id, owner_gid, jph, factory_gid) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, name, body.project_code.strip(), body.model_year,
                  body.suffix.strip(), body.description, body.status,
                 body.vehicle_model_gid,
                 body.team_id or current_user.get("team_id"), current_user["gid"],
                 body.jph, body.factory_gid)
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "name": name}}


@router.get("/members/matrix")
def get_members_matrix(current_user: dict = Depends(get_current_user)):
    """返回所有项目成员矩阵数据（人员×项目，含线体/角色信息）。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pm.user_gid, u.name, u.email, u.avatar_url, "
                "pm.project_gid, p.name AS project_name, "
                "pm.role, pm.scope_gid, "
                "be.title AS section_title "
                "FROM workmanship_auth_project_members pm "
                "JOIN workmanship_auth_users u ON pm.user_gid = u.gid "
                "JOIN workmanship_proj_projects p ON pm.project_gid = p.gid AND p.is_deleted = FALSE "
                "LEFT JOIN workmanship_bop_bop_entries be ON pm.scope_gid = be.gid "
                "ORDER BY u.name, p.name"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {
            "user_gid": r["user_gid"], "name": r["name"],
            "email": r["email"], "avatar_url": r["avatar_url"],
            "project_gid": r["project_gid"], "project_name": r["project_name"],
            "project_role": r["role"], "section_gid": r["scope_gid"],
            "section_title": r["section_title"],
        }
        for r in rows
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
                "SELECT pm.gid, pm.user_gid, u.name, u.email, u.avatar_url, "
                "pm.role, pm.scope_gid, pm.created_at "
                "FROM workmanship_auth_project_members pm JOIN workmanship_auth_users u ON pm.user_gid = u.gid "
                "WHERE pm.project_gid = %s ORDER BY pm.created_at",
                (gid,)
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {
            "gid": r["gid"], "user_gid": r["user_gid"], "name": r["name"],
            "email": r["email"], "avatar_url": r["avatar_url"],
            "project_role": r["role"], "section_gid": r["scope_gid"],
            "created_at": str(r["created_at"])
        }
        for r in rows
    ]}


@router.post("/{gid}/members", status_code=201)
def add_project_member(gid: str, body: AddMemberBody, current_user: dict = Depends(_PROJECT_WRITE)):
    member_gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_proj_projects WHERE gid = %s AND is_deleted = FALSE", (gid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="项目不存在")
            try:
                cur.execute(
                    "INSERT INTO workmanship_auth_project_members (gid, project_gid, user_gid, role, scope_gid) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (member_gid, gid, body.user_gid, body.project_role, body.section_gid)
                )
            except Exception:
                raise HTTPException(status_code=409, detail="该用户已是项目成员")
        conn.commit()
    return {"success": True, "data": {"gid": member_gid}}


@router.delete("/{gid}/members/{member_gid}")
def remove_project_member(gid: str, member_gid: str, current_user: dict = Depends(_PROJECT_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM workmanship_auth_project_members WHERE gid = %s AND project_gid = %s",
                (member_gid, gid)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="成员记录不存在")
        conn.commit()
    return {"success": True}


@router.get("/{gid}/bop-lines")
def get_project_bop_lines(gid: str, current_user: dict = Depends(get_current_user)):
    """返回项目活动 BOP 版本的线体（line_process）列表。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid FROM workmanship_bop_bop_versions "
                "WHERE project_gid = %s AND archived_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (gid,)
            )
            ver = cur.fetchone()
            if not ver:
                return {"success": True, "data": []}
            cur.execute(
                "SELECT gid, title, sort_order FROM workmanship_bop_bop_entries "
                "WHERE version_gid = %s AND node_type = 'line_process' AND is_deleted = FALSE "
                "ORDER BY sort_order , title",
                (ver["gid"],)
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "title": r["title"] or "（未命名线体）", "seq_no": r["sort_order"]}
        for r in rows
    ]}


@router.put("/{gid}/line-assignment")
def upsert_line_assignment(gid: str, body: LineAssignmentBody, current_user: dict = Depends(_PROJECT_WRITE)):
    """插槽式指派 project_owner 或 section_lead。传 user_gid=None 则清空该槽位。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_proj_projects WHERE gid = %s AND is_deleted = FALSE", (gid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="项目不存在")
            if body.slot == "project_owner":
                cur.execute(
                    "DELETE FROM workmanship_auth_project_members WHERE project_gid = %s AND role = 'project_manager'",
                    (gid,)
                )
                if body.user_gid:
                    mgid = str(next_gid())
                    cur.execute(
                        "INSERT INTO workmanship_auth_project_members (gid, project_gid, user_gid, role) "
                        "VALUES (%s, %s, %s, 'project_manager')",
                        (mgid, gid, body.user_gid)
                    )
            elif body.slot == "section_lead":
                if not body.section_gid:
                    raise HTTPException(status_code=400, detail="section_lead 需提供 section_gid")
                cur.execute(
                    "DELETE FROM workmanship_auth_project_members "
                    "WHERE project_gid = %s AND role = 'section_owner' AND scope_gid = %s",
                    (gid, body.section_gid)
                )
                if body.user_gid:
                    mgid = str(next_gid())
                    cur.execute(
                        "INSERT INTO workmanship_auth_project_members (gid, project_gid, user_gid, role, scope_type, scope_gid) "
                        "VALUES (%s, %s, %s, 'section_owner', 'section', %s)",
                        (mgid, gid, body.user_gid, body.section_gid)
                    )
            else:
                raise HTTPException(status_code=400, detail=f"无效 slot: {body.slot}")
        conn.commit()
    return {"success": True}
