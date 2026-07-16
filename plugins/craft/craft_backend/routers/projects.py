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
from backend.routers.deps import get_current_user, require_role, scope_visible_clause, _get_user_grants, _derive_org_role
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


class LineGrantBody(BaseModel):
    user_gid: Optional[str] = None
    line_gid: str


class CreateVehicleModelBody(BaseModel):
    name: str
    brand: str = ""
    platform: str = ""
    vehicle_type: str = ""
    team_id: Optional[str] = None


def _can_manage_project_lines(user: dict, project_gid: str) -> bool:
    """超管或项目管理员（project_manager）可以管理项目的线体权限。"""
    org_role = user.get("org_role") or _derive_org_role(user.get("system_role", "external"))
    if org_role == "super_admin":
        return True
    grants = _get_user_grants(user["gid"])
    for g in grants:
        if g.get("grant_type") == "project_admin" and g.get("scope_gid") == project_gid:
            return True
    # 也检查 project_members 表
    try:
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM workmanship_auth_project_members "
                    "WHERE project_gid = %s AND user_gid = %s",
                    (project_gid, user["gid"]),
                )
                if cur.fetchone():
                    return True
    except: pass
    return False


def _get_editable_line_gids(cur, user: dict, project_gid: str) -> set[str]:
    org_role = user.get("org_role") or _derive_org_role(user.get("system_role", "external"))
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

    grants = _get_user_grants(user["gid"])
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
            # 1. 项目成员（project_members 表）
            cur.execute(
                "SELECT pm.gid, pm.user_gid, u.name, u.email, u.avatar_url, "
                "pm.role, pm.scope_gid, pm.scope_type, pm.created_at, be.title AS line_title "
                "FROM workmanship_auth_project_members pm JOIN workmanship_auth_users u ON pm.user_gid = u.gid "
                "LEFT JOIN workmanship_bop_bop_entries be ON pm.scope_gid = be.gid "
                "WHERE pm.project_gid = %s",
                (gid,)
            )
            rows = list(cur.fetchall())
            # 2. 线体管理员（permission_grants 表，项目所有线体）
            cur.execute(
                "SELECT pg.gid, pg.grantee_gid AS user_gid, u.name, u.email, u.avatar_url, "
                "pg.scope_gid, pg.granted_at AS created_at, be.title AS line_title "
                "FROM workmanship_auth_permission_grants pg JOIN workmanship_auth_users u ON pg.grantee_gid = u.gid "
                "LEFT JOIN workmanship_bop_bop_entries be ON pg.scope_gid = be.gid "
                "WHERE pg.grant_type = 'section_lead' AND pg.scope_gid IN ("
                "  SELECT e.gid FROM workmanship_bop_bop_entries e "
                "  JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid "
                "  WHERE v.project_gid = %s AND v.archived_at IS NULL"
                ")",
                (gid,)
            )
            grant_rows = cur.fetchall()
    # 合并，去重 user_gid + scope_gid
    seen = set()
    result = []
    for r in rows:
        key = (r["user_gid"], r["scope_gid"] or "")
        if key not in seen:
            seen.add(key)
            result.append({
                "gid": r["gid"], "user_gid": r["user_gid"], "name": r["name"],
                "email": r["email"], "avatar_url": r["avatar_url"],
                "project_role": r["role"], "scope_gid": r["scope_gid"],
                "scope_type": r.get("scope_type") or "", "line_title": r.get("line_title") or "",
                "created_at": str(r["created_at"])
            })
    for r in grant_rows:
        key = (r["user_gid"], r["scope_gid"] or "")
        if key not in seen:
            seen.add(key)
            result.append({
                "gid": r["gid"], "user_gid": r["user_gid"], "name": r["name"],
                "email": r["email"], "avatar_url": r["avatar_url"],
                "project_role": "section_lead", "scope_gid": r["scope_gid"],
                "scope_type": "line", "line_title": r.get("line_title") or "",
                "created_at": str(r["created_at"])
            })
    return {"success": True, "data": result}


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
                    "INSERT INTO workmanship_auth_project_members (gid, project_gid, user_gid, role, scope_type, scope_gid) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (member_gid, gid, body.user_gid, body.project_role, 'project', body.section_gid)
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
    """按线体授予或撤销 section_lead grant。
    传入 line_gid 为任意一个线体 gid，会自动找到该项目下所有同名线体 gid 并批量操作。
    传 user_gid=None 则清空所有同名线体的管理员。
    """
    if not body.line_gid:
        raise HTTPException(status_code=400, detail="line_gid 不能为空")
    if not _can_manage_project_lines(current_user, gid):
        raise HTTPException(status_code=403, detail="权限不足")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_proj_projects WHERE gid = %s AND is_deleted = FALSE", (gid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="项目不存在")
            # 查这条线体的 title
            cur.execute(
                "SELECT title FROM workmanship_bop_bop_entries WHERE gid = %s AND node_type = 'line_process'",
                (body.line_gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="线体不存在")
            line_title = row["title"]
            # 找到该项目所有同名线体的 gid
            cur.execute(
                "SELECT e.gid FROM workmanship_bop_bop_entries e "
                "JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid "
                "WHERE v.project_gid = %s AND v.archived_at IS NULL "
                "AND e.node_type = 'line_process' AND e.is_deleted = FALSE AND e.title = %s",
                (gid, line_title)
            )
            all_line_gids = [r["gid"] for r in cur.fetchall()]
            if not all_line_gids:
                raise HTTPException(status_code=404, detail="线体不存在")
            # 删除所有同名线体的旧 grant
            ph = ",".join(["%s"] * len(all_line_gids))
            cur.execute(
                f"DELETE FROM workmanship_auth_permission_grants WHERE grant_type = 'section_lead' AND scope_gid IN ({ph})",
                all_line_gids,
            )
            # 批量插入新 grant
            if body.user_gid:
                values_sql = ",".join(["(%s,%s,'section_lead',%s,%s,'')"] * len(all_line_gids))
                flat = []
                for lg in all_line_gids:
                    flat.extend([str(next_gid()), body.user_gid, lg, current_user["gid"]])
                cur.execute(
                    f"INSERT INTO workmanship_auth_permission_grants (gid, grantee_gid, grant_type, scope_gid, granted_by, note) VALUES {values_sql}",
                    flat,
                )
        conn.commit()
    return {"success": True}
