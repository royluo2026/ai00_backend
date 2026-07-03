"""
backend/routers/std_op.py
──────────────────────────
标准工序库 API（std_operations）

端点：
  GET  /api/std_op/operations            → 工序列表（支持 status 过滤）
  POST /api/std_op/operations            → 创建工序
  GET  /api/std_op/operations/{gid}      → 工序详情
  PATCH /api/std_op/operations/{gid}     → 更新工序（版本号自动递增，标记下游 drift）
  DELETE /api/std_op/operations/{gid}    → 删除工序
  POST /api/std_op/operations/{gid}/publish   → 发布（draft→active）
  POST /api/std_op/operations/{gid}/deprecate → 废弃（active→deprecated）
  POST /api/std_op/operations/{gid}/clone-to-post → 克隆到 BOP 岗位
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.db.sequences import next_display_id
from backend.routers.deps import get_current_user, require_role, scope_visible_clause
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/std_op", tags=["std_op"])

_READ = require_role("super_admin", "team_admin", "project_admin",
                     "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "knowledge_admin")

# 可追踪 drift 的字段（std_op 字段名 → bop_operation 对应字段名）
_DRIFT_FIELD_MAP = {
    "name":          "op_name",
    "standard_time": "standard_time",
}


class CreateOpBody(BaseModel):
    code: str
    name: str
    standard_time: float = 0
    importance: Optional[str] = None
    description: str = ""
    level: str = ""
    vpps_attr: str = ""
    vpps: Optional[str] = None
    vpps_desc: str = ""
    torque_importance: str = ""
    vehicle_model: str = ""
    parent_vpps: str = ""
    steps: list = []
    required_tools: list = []
    parameters: dict = {}


class UpdateOpBody(BaseModel):
    name: Optional[str] = None
    standard_time: Optional[float] = None
    importance: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    vpps_attr: Optional[str] = None
    vpps: Optional[str] = None
    vpps_desc: Optional[str] = None
    torque_importance: Optional[str] = None
    vehicle_model: Optional[str] = None
    parent_vpps: Optional[str] = None
    steps: Optional[list] = None
    required_tools: Optional[list] = None
    parameters: Optional[dict] = None


class CloneToPostBody(BaseModel):
    post_gid: str
    seq_no: int = 0


def _std_op_row(row) -> dict:
    """RealDictRow → plain dict，含 version 字段"""
    return {
        "gid": row["gid"], "display_id": row.get("display_id") or "",
        "code": row["code"], "name": row["name"],
        "status": row["status"], "standard_time": row["standard_time"],
        "importance": row["importance"], "description": row["description"],
        "level": row.get("level") or "", "vpps_attr": row.get("vpps_attr") or "",
        "vpps": row.get("vpps") or "", "vpps_desc": row.get("vpps_desc") or "",
        "torque_importance": row.get("torque_importance") or "",
        "vehicle_model": row.get("vehicle_model") or "",
        "parent_vpps": row.get("parent_vpps") or "",
        "share_scope": row["share_scope"], "version": row["version"],
        "created_by": row.get("created_by") or "",
        "created_at": str(row["created_at"]),
    }


@router.get("/operations")
def list_operations(
    status: Optional[str] = Query(None),
    current_user: dict = Depends(_READ)
):
    scope_sql, scope_params = scope_visible_clause(current_user, owner_col="created_by", team_col="team_id")
    with get_conn() as conn:
        with conn.cursor() as cur:
            conditions = [scope_sql]
            params = list(scope_params)
            if status:
                conditions.append("status = %s")
                params.append(status)
            where = "WHERE " + " AND ".join(conditions)
            cur.execute(
                f"SELECT gid, display_id, code, name, status, standard_time, importance, description, "
                f"level, vpps_attr, vpps, vpps_desc, torque_importance, vehicle_model, parent_vpps, "
                f"share_scope, version, created_by, created_at "
                f"FROM workmanship_tpl_gbop_entries {where} ORDER BY code",
                params
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_std_op_row(r) for r in rows]}


@router.post("/operations", status_code=201)
def create_operation(body: CreateOpBody, current_user: dict = Depends(_WRITE)):
    gid = str(next_gid())
    display_id = f"S-C{next_display_id('std_op_display_seq'):08d}"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_tpl_gbop_entries "
                "(gid, display_id, code, name, standard_time, importance, description, "
                " level, vpps_attr, vpps, vpps_desc, torque_importance, vehicle_model, parent_vpps, "
                " steps, required_tools, parameters, created_by, team_id) "
                "VALUES (%s, %s, "
                "        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, display_id, body.code, body.name, body.standard_time, body.importance,
                 body.description, body.level, body.vpps_attr, body.vpps, body.vpps_desc,
                 body.torque_importance, body.vehicle_model, body.parent_vpps,
                 json.dumps(body.steps, ensure_ascii=False),
                 json.dumps(body.required_tools, ensure_ascii=False),
                 json.dumps(body.parameters, ensure_ascii=False),
                 current_user["gid"], current_user.get("team_id"))
            )
    return {"success": True, "data": {"gid": gid}}


@router.get("/operations/{gid}")
def get_operation(gid: str, current_user: dict = Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, display_id, code, name, status, standard_time, importance, description, "
                "steps, required_tools, parameters, created_by, version, created_at, updated_at "
                "FROM workmanship_tpl_gbop_entries WHERE gid = %s",
                (gid,)
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="标准工序不存在")
    return {"success": True, "data": {
        "gid": row["gid"], "display_id": row.get("display_id") or "",
        "code": row["code"], "name": row["name"],
        "status": row["status"], "standard_time": row["standard_time"],
        "importance": row["importance"], "description": row["description"],
        "steps": row["steps"], "required_tools": row["required_tools"],
        "parameters": row["parameters"], "created_by": row["created_by"],
        "version": row["version"],
        "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"])
    }}


@router.patch("/operations/{gid}")
def update_operation(gid: str, body: UpdateOpBody, current_user: dict = Depends(_WRITE)):
    updates = {}
    d = body.model_dump()
    for k, v in d.items():
        if v is not None:
            if isinstance(v, (list, dict)):
                updates[k] = json.dumps(v, ensure_ascii=False)
            else:
                updates[k] = v
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    json_fields = {"steps", "required_tools", "parameters"}
    set_parts = []
    vals = []
    for k, v in updates.items():
        if k in json_fields:
            set_parts.append(f"{k} = %s")
        else:
            set_parts.append(f"{k} = %s")
        vals.append(v)
    # 版本号递增
    set_parts.append("version = version + 1")
    set_parts.append("updated_at = NOW()")
    vals.append(gid)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_tpl_gbop_entries SET {', '.join(set_parts)} WHERE gid = %s",
                vals
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="标准工序不存在")
            cur.execute("SELECT version FROM workmanship_tpl_gbop_entries WHERE gid = %s", (gid,))
            row = cur.fetchone()
            new_version = row["version"]

            # V1 bop_operations drift-marking removed (table deprecated)
    return {"success": True}


@router.delete("/operations/{gid}")
def delete_operation(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_tpl_gbop_entries WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="标准工序不存在")
    return {"success": True}


@router.post("/operations/{gid}/publish")
def publish_operation(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_tpl_gbop_entries SET status = 'active', updated_at = NOW() "
                "WHERE gid = %s AND status = 'draft'",
                (gid,)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="工序不存在或状态不符")
    return {"success": True}


@router.post("/operations/{gid}/deprecate")
def deprecate_operation(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_tpl_gbop_entries SET status = 'deprecated', updated_at = NOW() "
                "WHERE gid = %s AND status = 'active'",
                (gid,)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="工序不存在或状态不符")
    return {"success": True}


@router.post("/operations/{gid}/clone-to-post", status_code=201)
def clone_to_post(gid: str, body: CloneToPostBody, current_user: dict = Depends(_READ)):
    """V1 clone-to-post 端点（bop_posts/bop_operations 已废弃，此端点保留签名但不执行）"""
    raise HTTPException(status_code=410, detail="V1 bop_posts/bop_operations 已废弃，请使用新 BOP entry API")
