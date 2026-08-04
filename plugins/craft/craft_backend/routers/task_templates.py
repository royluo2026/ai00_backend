"""
backend/routers/task_templates.py
──────────────────────────────────
任务模板 API（task_templates / task_template_items）

端点：
  GET    /api/task-templates                    → 模板列表
  POST   /api/task-templates                    → 创建模板
  GET    /api/task-templates/{gid}              → 模板详情（含 items）
  PATCH  /api/task-templates/{gid}              → 更新模板元信息
  DELETE /api/task-templates/{gid}              → 删除模板
  POST   /api/task-templates/{gid}/items        → 添加条目
  PATCH  /api/task-templates/items/{item_gid}   → 更新条目
  DELETE /api/task-templates/items/{item_gid}   → 删除条目
  POST   /api/task-templates/{gid}/instantiate  → 实例化（批量创建任务）
"""
import json
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import require_role
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/task-templates", tags=["task_templates"])

_READ  = require_role("super_admin", "team_admin", "project_admin",
                      "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "knowledge_admin")


# ── Pydantic 模型 ──────────────────────────────────────────────

class CreateTemplateBody(BaseModel):
    name: str
    description: str = ""
    scope: str = "system"   # system|team|personal


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
    start_date: str                          # ISO date string YYYY-MM-DD
    assignee_map: dict = {}                  # { "角色名": "user_gid" }
    title_vars: dict = {}                    # { "project_name": "P12345" }
    owner_user_gid: Optional[str] = None     # 创建人 gid


# ── 工具函数 ──────────────────────────────────────────────────

def _render_title(pattern: str, vars_: dict) -> str:
    """把 {{key}} 替换为 title_vars 里的值，缺失的变量保留原样"""
    def replacer(m):
        key = m.group(1).strip()
        return str(vars_.get(key, m.group(0)))
    return re.sub(r'\{\{(.+?)\}\}', replacer, pattern)


def _calc_due_date(start_date_str: str, offset_days: Optional[int]) -> Optional[str]:
    if offset_days is None:
        return None
    try:
        d = date.fromisoformat(start_date_str) + timedelta(days=offset_days)
        return d.isoformat()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# 模板 CRUD
# ══════════════════════════════════════════════════════════════

@router.get("")
def list_templates(current_user: dict = Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, description, scope, version, is_active, created_at, updated_at "
                "FROM workmanship_work_task_templates WHERE is_active = TRUE ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("", status_code=201)
def create_template(body: CreateTemplateBody, current_user: dict = Depends(_WRITE)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_work_task_templates (gid, name, description, scope, owner_gid) "
                "VALUES (%s, %s, %s, %s, %s)",
                (gid, body.name, body.description, body.scope, current_user["gid"])
            )
    return {"success": True, "data": {"gid": gid}}


@router.get("/{gid}")
def get_template(gid: str, current_user: dict = Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, description, scope, version, is_active, created_at, updated_at "
                "FROM workmanship_work_task_templates WHERE gid = %s",
                (gid,)
            )
            tpl = cur.fetchone()
            if not tpl:
                raise HTTPException(404, "模板不存在")
            tpl = dict(tpl)

            cur.execute(
                "SELECT gid, title_pattern, description, priority, assignee_role, "
                "due_offset_days, share_scope, sort_order "
                "FROM workmanship_work_task_template_items WHERE template_gid = %s ORDER BY sort_order",
                (gid,)
            )
            tpl["items"] = [dict(r) for r in cur.fetchall()]
    return {"success": True, "data": tpl}


@router.patch("/{gid}")
def update_template(gid: str, body: UpdateTemplateBody, current_user: dict = Depends(_WRITE)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "无更新字段")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_work_task_templates SET {set_clause}, updated_at=NOW(), version=version+1 "
                "WHERE gid=%s",
                list(updates.values()) + [gid]
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "模板不存在")
    return {"success": True}


@router.delete("/{gid}", status_code=204)
def delete_template(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_work_task_templates WHERE gid=%s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(404, "模板不存在")


# ══════════════════════════════════════════════════════════════
# 条目 CRUD
# ══════════════════════════════════════════════════════════════

@router.post("/{template_gid}/items", status_code=201)
def add_item(template_gid: str, body: CreateItemBody, current_user: dict = Depends(_WRITE)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_work_task_template_items "
                "(gid, template_gid, title_pattern, description, priority, "
                " assignee_role, due_offset_days, share_scope, sort_order) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, template_gid, body.title_pattern, body.description,
                 body.priority, body.assignee_role, body.due_offset_days,
                 body.share_scope, body.sort_order)
            )
    return {"success": True, "data": {"gid": gid}}


@router.patch("/items/{item_gid}")
def update_item(item_gid: str, body: UpdateItemBody, current_user: dict = Depends(_WRITE)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "无更新字段")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_work_task_template_items SET {set_clause} WHERE gid=%s",
                list(updates.values()) + [item_gid]
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "条目不存在")
    return {"success": True}


@router.delete("/items/{item_gid}", status_code=204)
def delete_item(item_gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_work_task_template_items WHERE gid=%s", (item_gid,))
            if cur.rowcount == 0:
                raise HTTPException(404, "条目不存在")


# ══════════════════════════════════════════════════════════════
# 实例化：批量创建任务
# ══════════════════════════════════════════════════════════════

@router.post("/{gid}/instantiate", status_code=201)
def instantiate(gid: str, body: InstantiateBody, current_user: dict = Depends(_READ)):
    """
    将模板中所有条目实例化为任务行：
    - title_pattern 中的 {{变量}} 被替换
    - assignee_role 被映射为具体 user_gid
    - due_offset_days 加上 start_date 得到 due_date
    - 记录 template_item_gid 和 template_source_version
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 读取模板版本
            cur.execute(
                "SELECT version FROM workmanship_work_task_templates WHERE gid=%s AND is_active=TRUE",
                (gid,)
            )
            tpl = cur.fetchone()
            if not tpl:
                raise HTTPException(404, "模板不存在或已停用")
            tpl_version = tpl["version"]

            # 读取所有条目
            cur.execute(
                "SELECT gid, title_pattern, description, priority, assignee_role, "
                "due_offset_days, share_scope "
                "FROM workmanship_work_task_template_items WHERE template_gid=%s ORDER BY sort_order",
                (gid,)
            )
            items = [dict(r) for r in cur.fetchall()]

            created = []
            for item in items:
                title = _render_title(item["title_pattern"], body.title_vars)
                due_date = _calc_due_date(body.start_date, item["due_offset_days"])
                assignee_gid = body.assignee_map.get(item["assignee_role"]) if item["assignee_role"] else None
                owner_gid = body.owner_user_gid or current_user["gid"]

                task_gid = str(next_gid())
                cur.execute(
                    """
                    INSERT INTO workmanship_proj_tasks
                      (gid, title, description, owner_user_gid, project_gid,
                       priority, share_scope, due_date,
                       template_item_gid, template_source_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (task_gid, title, item["description"], owner_gid,
                     body.project_gid, item["priority"], item["share_scope"],
                     due_date, item["gid"], tpl_version)
                )
                created.append({
                    "gid": task_gid,
                    "title": title,
                    "due_date": due_date,
                    "assignee_gid": assignee_gid,
                    "template_item_gid": item["gid"],
                })

    return {"success": True, "data": created, "count": len(created)}
