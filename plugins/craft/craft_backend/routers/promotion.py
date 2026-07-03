"""
backend/routers/promotion.py
──────────────────────────────
本地⇄云端提升引擎 API

任务端点：
  GET    /api/tasks                → 列出云端任务
  POST   /api/tasks                → 直接创建云端任务
  GET    /api/tasks/{gid}          → 获取单条云端任务
  PUT    /api/tasks/{gid}          → 更新云端任务
  DELETE /api/tasks/{gid}          → 软删除云端任务
  POST   /api/tasks/promote        → 将本地任务提升到云端

问题端点（与任务对称）：
  GET    /api/issues
  POST   /api/issues
  GET    /api/issues/{gid}
  PUT    /api/issues/{gid}
  DELETE /api/issues/{gid}
  POST   /api/issues/promote
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.db.sequences import next_display_id
from backend.routers.deps import get_current_user, task_scope_clauses
from backend.utils.gid import next_gid
from backend.utils.change_log import record_changes
from backend.utils.follow_trigger import notify_followers, RESOLVED_STATUSES

router = APIRouter(tags=["promotion"])


# ── 请求体模型 ────────────────────────────────────────────────────────────────

class TaskBody(BaseModel):
    title: str
    description: str = ""
    owner_gid: str = ""
    assignee_team_gid: Optional[str] = None
    project_gid: Optional[str] = None
    status: str = "pending"
    priority: str = "normal"
    source_ref: dict = {}
    review_date: Optional[str] = None
    meeting_level: str = "none"
    meeting_doc_link: Optional[str] = None
    progress_logs: list = []
    due_date: Optional[str] = None
    plan_start: Optional[str] = None
    plan_end: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    share_scope: str = "project"
    list_gid: Optional[str] = None
    local_gid: Optional[str] = None
    local_created_at: Optional[float] = None
    attachments: list = []
    scheduled_date: Optional[str] = None
    scheduled_start_time: Optional[str] = None
    time_estimate: Optional[int] = None
    is_deleted: bool = False
    parent_task_gid: Optional[str] = None
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
    completion: int = 0
    node_type: str = "normal"
    canvas_icon: str = "star"
    feishu_assignee_open_id: Optional[str] = None
    feishu_assignee_name:     Optional[str] = None
    feishu_group_chat_id:     Optional[str] = None
    feishu_group_name:        Optional[str] = None
    feishu_groups:            list = []
    feishu_docs:              list = []


class IssueBody(BaseModel):
    title: str
    description: str = ""
    severity: str = "low"
    status: str = "open"
    owner_gid: str = ""
    assignee_team_gid: Optional[str] = None
    project_gid: Optional[str] = None
    tracking_refs: list = []
    occurrence_root_cause: Optional[str] = None
    escape_root_cause: Optional[str] = None
    interim_action: Optional[str] = None
    permanent_action: Optional[str] = None
    source_ref: dict = {}
    related_task_gid: Optional[str] = None
    related_knowledge_gid: Optional[str] = None
    approval_order_gid: Optional[str] = None
    bop_entry_gid: Optional[str] = None
    share_scope: str = "project"
    list_gid: Optional[str] = None
    attachments: list = []
    feishu_assignee_open_id: Optional[str] = None
    feishu_assignee_name:     Optional[str] = None
    feishu_group_chat_id:     Optional[str] = None
    feishu_group_name:        Optional[str] = None
    feishu_groups:            list = []
    feishu_docs:              list = []


class IssuePromoteBody(IssueBody):
    local_gid: Optional[str] = None
    local_created_at: Optional[float] = None


class TaskPromoteBody(TaskBody):
    pass  # TaskBody already includes local_gid / local_created_at


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _row_to_task(r: dict) -> dict:
    return {
        "gid":                r["gid"],
        "display_id":         r.get("display_id") or "",
        "title":              r["title"],
        "description":        r["description"],
        "owner_gid":          r["owner_gid"],
        "owner_user_gid":     r["owner_user_gid"],
        "owner_name":         r.get("owner_name") or "",
        "assignee_team_gid":  r["assignee_team_gid"],
        "project_gid":        r["project_gid"],
        "status":             r["status"],
        "priority":           r["priority"],
        "source_ref":         r["source_ref"] or {},
        "review_date":        r["review_date"],
        "meeting_level":      r["meeting_level"],
        "meeting_doc_link":   r["meeting_doc_link"],
        "progress_logs":      r["progress_logs"] or [],
        "due_date":           r["due_date"],
        "plan_start":         r["plan_start"],
        "plan_end":           r["plan_end"],
        "actual_start":       r["actual_start"],
        "actual_end":         r["actual_end"],
        "share_scope":        r["share_scope"],
        "list_gid":           r.get("list_gid"),
        "attachments":        r.get("attachments") or [],
        "scheduled_date":       r.get("scheduled_date"),
        "scheduled_start_time": r.get("scheduled_start_time"),
        "time_estimate":        r.get("time_estimate"),
        "is_deleted":           bool(r.get("is_deleted", False)),
        "parent_task_gid":      r.get("parent_task_gid"),
        "canvas_x":             r.get("canvas_x"),
        "canvas_y":             r.get("canvas_y"),
        "completion":           r.get("completion") or 0,
        "node_type":            r.get("node_type") or "normal",
        "canvas_icon":          r.get("canvas_icon") or "star",
        "feishu_assignee_open_id": r.get("feishu_assignee_open_id"),
        "feishu_assignee_name":    r.get("feishu_assignee_name"),
        "feishu_group_chat_id":    r.get("feishu_group_chat_id"),
        "feishu_group_name":       r.get("feishu_group_name"),
        "feishu_groups":           r.get("feishu_groups") or [],
        "feishu_docs":             r.get("feishu_docs") or [],
        "created_at":         str(r["created_at"]),
        "updated_at":         str(r["updated_at"]),
    }


def _row_to_issue(r: dict) -> dict:
    return {
        "gid":                    r["gid"],
        "display_id":             r.get("display_id") or "",
        "title":                  r["title"],
        "description":            r["description"],
        "severity":               r["severity"],
        "status":                 r["status"],
        "owner_gid":              r["owner_gid"],
        "owner_user_gid":         r["owner_user_gid"],
        "assignee_team_gid":      r["assignee_team_gid"],
        "project_gid":            r["project_gid"],
        "tracking_refs":          r["tracking_refs"] or [],
        "occurrence_root_cause":  r["occurrence_root_cause"],
        "escape_root_cause":      r["escape_root_cause"],
        "interim_action":         r["interim_action"],
        "permanent_action":       r["permanent_action"],
        "source_ref":             r["source_ref"] or {},
        "related_task_gid":       r["related_task_gid"],
        "related_knowledge_gid":  r["related_knowledge_gid"],
        "approval_order_gid":     r["approval_order_gid"],
        "bop_entry_gid":          r.get("bop_entry_gid"),
        "share_scope":            r["share_scope"],
        "list_gid":               r.get("list_gid"),
        "attachments":            r.get("attachments") or [],
        "feishu_assignee_open_id": r.get("feishu_assignee_open_id"),
        "feishu_assignee_name":    r.get("feishu_assignee_name"),
        "feishu_group_chat_id":    r.get("feishu_group_chat_id"),
        "feishu_group_name":       r.get("feishu_group_name"),
        "feishu_groups":           r.get("feishu_groups") or [],
        "feishu_docs":             r.get("feishu_docs") or [],
        "created_at":             str(r["created_at"]),
        "updated_at":             str(r["updated_at"]),
    }


def _verify_project_access(conn, project_gid: Optional[str], user_gid: str) -> bool:
    """检查用户是否是项目成员（或项目为 None 时直接通过）。"""
    if not project_gid:
        return True
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM workmanship_auth_project_members WHERE project_gid = %s AND user_gid = %s",
            (project_gid, user_gid),
        )
        return cur.fetchone() is not None


# ══════════════════════════════════════════════════════════════════════════════
# 任务 CRUD + 提升
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/tasks")
def list_cloud_tasks(
    project_gid: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    list_gid: Optional[str] = Query(None),
    scheduled_date_from: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page_size: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            scope_clause, scope_params = task_scope_clauses(
                uid, current_user.get("team_id") or ""
            )
            clauses = [scope_clause, "t.deleted_at IS NULL"]
            params = scope_params
            if project_gid:
                clauses.append("t.project_gid = %s")
                params.append(project_gid)
            if status:
                clauses.append("t.status = %s")
                params.append(status)
            if list_gid:
                clauses.append("t.list_gid = %s")
                params.append(list_gid)
            if scheduled_date_from:
                clauses.append("t.scheduled_date >= %s")
                clauses.append("t.is_deleted = FALSE")
                params.append(scheduled_date_from)
            if q:
                clauses.append("t.title LIKE %s")
                params.append(f"%{q}%")
            where = " AND ".join(clauses)
            limit_clause = f" LIMIT {int(page_size)}" if page_size else ""
            cur.execute(
                f"SELECT t.*, u.name AS owner_name FROM workmanship_proj_tasks t "
                f"LEFT JOIN workmanship_auth_users u ON t.owner_user_gid = u.gid "
                f"WHERE {where} ORDER BY t.created_at DESC{limit_clause}",
                params,
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_row_to_task(dict(r)) for r in rows]}


@router.post("/api/tasks", status_code=201)
def create_cloud_task(body: TaskBody, current_user: dict = Depends(get_current_user)):
    import logging as _logging
    _dbg = _logging.getLogger("promotion.create_task")
    _dbg.setLevel(_logging.DEBUG)
    try:
        gid = str(next_gid())
        _dbg.warning("DEBUG step1: gid=%s", gid)
    except Exception as e:
        _dbg.warning("DEBUG step1 FAILED: %s", e, exc_info=True)
        raise
    try:
        display_id = f"T-C{next_display_id('proj_tasks_display_seq'):08d}"
        _dbg.warning("DEBUG step2: display_id=%s", display_id)
    except Exception as e:
        _dbg.warning("DEBUG step2 FAILED: %s", e, exc_info=True)
        raise
    uid = current_user["gid"]
    _dbg.warning("DEBUG step3: uid=%s", uid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            _dbg.warning("DEBUG step4: about to INSERT")
            cur.execute(
                """
                INSERT INTO workmanship_proj_tasks (
                    gid, display_id, title, description, owner_gid, owner_user_gid,
                    assignee_team_gid, project_gid, status, priority,
                    source_ref, review_date, meeting_level, meeting_doc_link,
                    progress_logs, due_date, plan_start, plan_end,
                    actual_start, actual_end, share_scope, list_gid, attachments,
                    canvas_x, canvas_y, node_type, canvas_icon
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    gid, display_id, body.title, body.description, body.owner_gid, uid,
                    body.assignee_team_gid, body.project_gid, body.status, body.priority,
                    json.dumps(body.source_ref), body.review_date, body.meeting_level,
                    body.meeting_doc_link, json.dumps(body.progress_logs),
                    body.due_date, body.plan_start, body.plan_end,
                    body.actual_start, body.actual_end, body.share_scope, body.list_gid,
                    json.dumps(body.attachments),
                    body.canvas_x, body.canvas_y, body.node_type, body.canvas_icon,
                ),
            )
            _dbg.warning("DEBUG step5: INSERT ok, about to SELECT")
            cur.execute(
                "SELECT t.*, u.name AS owner_name FROM workmanship_proj_tasks t "
                "LEFT JOIN workmanship_auth_users u ON t.owner_user_gid = u.gid "
                "WHERE t.gid = %s", (gid,)
            )
            row = cur.fetchone()
            _dbg.warning("DEBUG step6: SELECT ok, row=%s", row is not None)
    return {"success": True, "data": _row_to_task(dict(row)) if row else {"gid": gid}}


@router.get("/api/tasks/promote")
def get_promote_placeholder():
    """防止 GET /api/tasks/promote 被 /api/tasks/{gid} 路由捕获。"""
    return {"detail": "POST to this endpoint to promote a local task"}


@router.post("/api/tasks/promote", status_code=201)
def promote_task(body: TaskPromoteBody, current_user: dict = Depends(get_current_user)):
    """将本地任务提升到云端 PG。前端随后调用本地 bridge mark_task_migrated。"""
    gid = str(next_gid())
    display_id = f"T-C{next_display_id('proj_tasks_display_seq'):08d}"
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workmanship_proj_tasks (
                    gid, display_id, title, description, owner_gid, owner_user_gid,
                    assignee_team_gid, project_gid, status, priority,
                    source_ref, review_date, meeting_level, meeting_doc_link,
                    progress_logs, due_date, plan_start, plan_end,
                    actual_start, actual_end, share_scope, list_gid
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    gid, display_id, body.title, body.description, body.owner_gid, uid,
                    body.assignee_team_gid, body.project_gid, body.status, body.priority,
                    json.dumps(body.source_ref), body.review_date, body.meeting_level,
                    body.meeting_doc_link, json.dumps(body.progress_logs),
                    body.due_date, body.plan_start, body.plan_end,
                    body.actual_start, body.actual_end, body.share_scope, body.list_gid,
                ),
            )
    return {"success": True, "data": {"cloud_gid": gid, "local_gid": body.local_gid}}


@router.get("/api/tasks/{gid}")
def get_cloud_task(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_proj_tasks WHERE gid = %s", (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": _row_to_task(dict(row))}


@router.put("/api/tasks/{gid}")
@router.patch("/api/tasks/{gid}")
def update_cloud_task(gid: str, body: dict, current_user: dict = Depends(get_current_user)):
    allowed = {
        "title", "description", "status", "priority", "review_date",
        "meeting_level", "meeting_doc_link", "due_date", "plan_start",
        "plan_end", "actual_start", "actual_end", "share_scope",
        "assignee_team_gid", "project_gid", "attachments", "list_gid",
        "scheduled_date", "scheduled_start_time", "time_estimate", "is_deleted",
        "parent_task_gid", "canvas_x", "canvas_y", "completion", "node_type", "canvas_icon",
        "feishu_assignee_open_id", "feishu_assignee_name",
        "feishu_group_chat_id", "feishu_group_name",
        "feishu_groups", "feishu_docs",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新的字段")

    # JSONB 字段必须序列化为 JSON 字符串，否则 psycopg2 无法适配 list/dict
    _JSONB_TASK_FIELDS = {"attachments", "feishu_groups", "feishu_docs"}
    for f in _JSONB_TASK_FIELDS:
        if f in updates and not isinstance(updates[f], str):
            updates[f] = json.dumps(updates[f], ensure_ascii=False)

    # 附件编辑权限：仅 owner 或 admin 可修改
    if "attachments" in updates:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT owner_user_gid FROM workmanship_proj_tasks WHERE gid = %s", (gid,))
                task_row = cur.fetchone()
        owner_gid   = (task_row or {}).get("owner_user_gid", "")
        user_gid    = current_user.get("gid", "")
        user_role   = current_user.get("system_role", "")
        if owner_gid and owner_gid != user_gid and user_role not in ("super_admin", "team_admin"):
            raise HTTPException(status_code=403, detail="只有负责人或管理员可以编辑附件")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    set_clause += ", updated_at = NOW()"
    params = list(updates.values()) + [gid]

    # ── 主更新（独立事务，commit 后不受辅助操作影响）────────────────
    old_row = None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_proj_tasks WHERE gid = %s", (gid,))
            old_row = cur.fetchone()
        if old_row is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_proj_tasks SET {set_clause} WHERE gid = %s", params)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="任务不存在")
        # get_conn() 上下文管理器退出时自动 commit

    # ── 变更日志（独立事务，失败不回滚主更新）───────────────────────
    try:
        changes = {
            field: (old_row.get(field), updates[field])
            for field in updates
            if field not in ("attachments",)
        }
        with get_conn() as conn:
            record_changes(
                conn, "task", gid,
                old_row.get("list_gid") or updates.get("list_gid"),
                current_user["gid"],
                changes,
            )
    except Exception:
        pass

    # ── 关注者通知（独立事务，失败不回滚主更新）────────────────────
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title FROM workmanship_proj_tasks WHERE gid = %s", (gid,))
                row = cur.fetchone()
            title = row["title"] if row else gid
            events = ["any_change"]
            new_status = updates.get("status")
            if new_status:
                events.append("status_change")
                if new_status.lower() in RESOLVED_STATUSES:
                    events.append("resolved")
            if "assignee_team_gid" in updates:
                events.append("assigned_to_me")
            notify_followers(conn, "task", gid, title, events,
                             actor_user_gid=current_user["gid"])
    except Exception:
        pass

    return {"success": True}


@router.delete("/api/tasks/{gid}")
def delete_cloud_task(gid: str, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE workmanship_proj_tasks SET deleted_at = NOW()
                   WHERE gid = %s AND owner_user_gid = %s AND deleted_at IS NULL""",
                (gid, uid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="任务不存在或无权限")
        conn.commit()
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# 问题 CRUD + 提升
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/issues")
def list_cloud_issues(
    project_gid: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    list_gid: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page_size: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            scope_clause, scope_params = task_scope_clauses(
                uid, current_user.get("team_id") or "", alias="i"
            )
            clauses = [scope_clause]
            params = scope_params
            if project_gid:
                clauses.append("i.project_gid = %s")
                params.append(project_gid)
            if status:
                clauses.append("i.status = %s")
                params.append(status)
            if list_gid:
                clauses.append("i.list_gid = %s")
                params.append(list_gid)
            if q:
                clauses.append("i.title LIKE %s")
                params.append(f"%{q}%")
            where = " AND ".join(clauses)
            limit_clause = f" LIMIT {int(page_size)}" if page_size else ""
            cur.execute(
                f"SELECT i.* FROM workmanship_proj_issues i WHERE {where} ORDER BY i.created_at DESC{limit_clause}",
                params,
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_row_to_issue(dict(r)) for r in rows]}


@router.post("/api/issues", status_code=201)
def create_cloud_issue(body: IssueBody, current_user: dict = Depends(get_current_user)):
    gid = str(next_gid())
    display_id = f"I-C{next_display_id('proj_issues_display_seq'):08d}"
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workmanship_proj_issues (
                    gid, display_id, title, description, severity, status,
                    owner_gid, owner_user_gid, assignee_team_gid, project_gid,
                    tracking_refs, occurrence_root_cause, escape_root_cause,
                    interim_action, permanent_action, source_ref,
                    related_task_gid, related_knowledge_gid, approval_order_gid,
                    bop_entry_gid, share_scope, list_gid, attachments
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    gid, display_id, body.title, body.description, body.severity, body.status,
                    body.owner_gid, uid, body.assignee_team_gid, body.project_gid,
                    json.dumps(body.tracking_refs), body.occurrence_root_cause,
                    body.escape_root_cause, body.interim_action, body.permanent_action,
                    json.dumps(body.source_ref), body.related_task_gid,
                    body.related_knowledge_gid, body.approval_order_gid,
                    body.bop_entry_gid, body.share_scope, body.list_gid,
                    json.dumps(body.attachments),
                ),
            )
    return {"success": True, "data": {"gid": gid}}


@router.get("/api/issues/promote")
def get_issue_promote_placeholder():
    return {"detail": "POST to this endpoint to promote a local issue"}


@router.post("/api/issues/promote", status_code=201)
def promote_issue(body: IssuePromoteBody, current_user: dict = Depends(get_current_user)):
    """将本地问题提升到云端 PG。前端随后调用本地 bridge mark_issue_migrated。"""
    gid = str(next_gid())
    display_id = f"I-C{next_display_id('proj_issues_display_seq'):08d}"
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workmanship_proj_issues (
                    gid, display_id, title, description, severity, status,
                    owner_gid, owner_user_gid, assignee_team_gid, project_gid,
                    tracking_refs, occurrence_root_cause, escape_root_cause,
                    interim_action, permanent_action, source_ref,
                    related_task_gid, related_knowledge_gid, approval_order_gid,
                    bop_entry_gid, share_scope, list_gid, attachments
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    gid, display_id, body.title, body.description, body.severity, body.status,
                    body.owner_gid, uid, body.assignee_team_gid, body.project_gid,
                    json.dumps(body.tracking_refs), body.occurrence_root_cause,
                    body.escape_root_cause, body.interim_action, body.permanent_action,
                    json.dumps(body.source_ref), body.related_task_gid,
                    body.related_knowledge_gid, body.approval_order_gid,
                    body.bop_entry_gid, body.share_scope, body.list_gid,
                    json.dumps(body.attachments),
                ),
            )
    return {"success": True, "data": {"cloud_gid": gid, "local_gid": body.local_gid}}


@router.get("/api/issues/{gid}")
def get_cloud_issue(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_proj_issues WHERE gid = %s", (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="问题不存在")
    return {"success": True, "data": _row_to_issue(dict(row))}


@router.put("/api/issues/{gid}")
@router.patch("/api/issues/{gid}")
def update_cloud_issue(gid: str, body: dict, current_user: dict = Depends(get_current_user)):
    allowed = {
        "title", "description", "severity", "status", "assignee_team_gid",
        "project_gid", "occurrence_root_cause", "escape_root_cause",
        "interim_action", "permanent_action", "related_task_gid",
        "related_knowledge_gid", "approval_order_gid", "bop_entry_gid",
        "share_scope", "attachments", "list_gid", "scheduled_date",
        "feishu_assignee_open_id", "feishu_assignee_name",
        "feishu_group_chat_id", "feishu_group_name",
        "feishu_groups", "feishu_docs",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新的字段")

    # JSONB 字段必须序列化为 JSON 字符串，否则 psycopg2 无法适配 list/dict
    _JSONB_ISSUE_FIELDS = {"attachments", "feishu_groups", "feishu_docs"}
    for f in _JSONB_ISSUE_FIELDS:
        if f in updates and not isinstance(updates[f], str):
            updates[f] = json.dumps(updates[f], ensure_ascii=False)

    # 附件编辑权限：仅 owner 或 admin 可修改
    if "attachments" in updates:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT owner_user_gid FROM workmanship_proj_issues WHERE gid = %s", (gid,))
                issue_row = cur.fetchone()
        owner_gid   = (issue_row or {}).get("owner_user_gid", "")
        user_gid    = current_user.get("gid", "")
        user_role   = current_user.get("system_role", "")
        if owner_gid and owner_gid != user_gid and user_role not in ("super_admin", "team_admin"):
            raise HTTPException(status_code=403, detail="只有负责人或管理员可以编辑附件")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    set_clause += ", updated_at = NOW()"
    params = list(updates.values()) + [gid]

    # 主 UPDATE — 独立事务
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_proj_issues WHERE gid = %s", (gid,))
            old_row = cur.fetchone()
        if old_row is None:
            raise HTTPException(status_code=404, detail="问题不存在")
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_proj_issues SET {set_clause} WHERE gid = %s", params)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="问题不存在")

    # 写入变更日志 — 独立事务，失败不影响主更新
    try:
        changes = {
            field: (old_row.get(field), updates[field])
            for field in updates
            if field not in ("attachments",)
        }
        with get_conn() as conn:
            record_changes(
                conn, "issue", gid,
                old_row.get("list_gid") or updates.get("list_gid"),
                current_user["gid"],
                changes,
            )
    except Exception:
        pass

    # 触发关注者通知 — 独立事务，失败不影响主更新
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title FROM workmanship_proj_issues WHERE gid = %s", (gid,))
                row = cur.fetchone()
            title = row["title"] if row else gid
            events = ["any_change"]
            new_status = updates.get("status")
            if new_status:
                events.append("status_change")
                if new_status.lower() in RESOLVED_STATUSES:
                    events.append("resolved")
            if "assignee_team_gid" in updates:
                events.append("assigned_to_me")
            notify_followers(conn, "issue", gid, title, events,
                             actor_user_gid=current_user["gid"])
    except Exception:
        pass

    return {"success": True}


@router.delete("/api/issues/{gid}")
def delete_cloud_issue(gid: str, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM workmanship_work_item_entries WHERE item_type = 'issue' AND item_gid = %s",
                (gid,),
            )
            cur.execute(
                "DELETE FROM workmanship_proj_issues WHERE gid = %s AND owner_user_gid = %s",
                (gid, uid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="问题不存在或无权限")
    return {"success": True}


# ── 任务依赖关系（画布连线）────────────────────────────────────────────────────

class TaskDepBody(BaseModel):
    source_gid:    str
    target_gid:    str
    edge_type:     str = "prerequisite"
    dep_condition: str = "done"
    dep_group:     Optional[str] = None
    label:         str = ""


@router.get("/api/task-dependencies")
def list_task_dependencies(
    list_gid: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT td.*
                FROM workmanship_proj_task_dependencies td
                WHERE td.source_gid IN (
                    SELECT gid FROM workmanship_proj_tasks WHERE list_gid = %s
                ) OR td.target_gid IN (
                    SELECT gid FROM workmanship_proj_tasks WHERE list_gid = %s
                )
                ORDER BY td.created_at
            """, (list_gid, list_gid))
            rows = cur.fetchall()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("/api/task-dependencies")
def create_task_dependency(body: TaskDepBody, current_user: dict = Depends(get_current_user)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO workmanship_proj_task_dependencies
                    (gid, source_gid, target_gid, edge_type, dep_condition, dep_group, label)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (gid, body.source_gid, body.target_gid,
                  body.edge_type, body.dep_condition, body.dep_group, body.label))
            cur.execute(
                "SELECT gid, source_gid, target_gid, edge_type, dep_condition, dep_group, label "
                "FROM workmanship_proj_task_dependencies WHERE gid = %s",
                (gid,),
            )
            row = cur.fetchone()
        conn.commit()
    return {"success": True, "data": dict(row)}


@router.put("/api/task-dependencies/{gid}")
def update_task_dependency(
    gid: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    allowed = {"edge_type", "dep_condition", "dep_group", "label"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新的字段")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    params = list(updates.values()) + [gid]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_proj_task_dependencies SET {set_clause} WHERE gid = %s", params)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="依赖不存在")
        conn.commit()
    return {"success": True}


@router.delete("/api/task-dependencies/{gid}")
def delete_task_dependency(gid: str, current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_proj_task_dependencies WHERE gid = %s", (gid,))
        conn.commit()
    return {"success": True}
