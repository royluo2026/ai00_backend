"""
backend/routers/approval.py
────────────────────────────
审批 API（approval_orders）

端点：
  GET  /api/approval/orders              → 审批单列表
  POST /api/approval/orders              → 创建审批单
  GET  /api/approval/orders/{gid}        → 审批单详情
  POST /api/approval/orders/{gid}/start  → 提交审批（start_review）
  POST /api/approval/orders/{gid}/approve → 通过审批
  POST /api/approval/orders/{gid}/reject  → 拒绝审批
  POST /api/approval/orders/{gid}/withdraw → 撤回审批
  POST /api/approval/orders/scope_upgrade → 申请 share_scope 提升
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user, require_role, scope_visible_clause
from backend.platform_sdk.ids import next_gid
from backend.platform_sdk.identity import find_active_user_by_role

router = APIRouter(prefix="/api/approval", tags=["approval"])
_log = __import__('logging').getLogger(__name__)

_SUBMIT = require_role("super_admin", "team_admin", "project_admin",
                       "rule_admin", "knowledge_admin", "member")
_APPROVE = require_role("super_admin", "team_admin", "project_admin")


class CreateOrderBody(BaseModel):
    title: str
    order_type: str = "general"
    project_gid: Optional[str] = None
    reviewer_gid: Optional[str] = None
    source_ref: Optional[str] = None
    content: dict = {}


class ScopeUpgradeBody(BaseModel):
    item_type: str      # task|issue|project|knowledge|rule|std_op|work_plan
    item_gid: str
    item_title: str
    current_scope: str  # local|project|team|global
    target_scope: str   # local|project|team|global
    reason: str = ""


class OpinionBody(BaseModel):
    comment: str = ""


@router.get("/orders")
def list_orders(
    status: Optional[str] = Query(None),
    project_gid: Optional[str] = Query(None),
    current_user: dict = Depends(_SUBMIT)
):
    scope_sql, scope_params = scope_visible_clause(current_user, owner_col="applicant_gid", team_col="project_gid")
    with get_conn() as conn:
        with conn.cursor() as cur:
            conditions = [scope_sql]
            params = list(scope_params)
            if status:
                conditions.append("status = %s")
                params.append(status)
            if project_gid:
                conditions.append("project_gid = %s")
                params.append(project_gid)
            where = "WHERE " + " AND ".join(conditions)
            cur.execute(
                f"SELECT gid, project_gid, order_type, title, applicant_gid, "
                f"reviewer_gid, status, source_ref, share_scope, created_at, updated_at "
                f"FROM workmanship_proj_approval_orders {where} ORDER BY updated_at DESC",
                params
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {
            "gid": r[0], "project_gid": r[1], "order_type": r[2], "title": r[3],
            "applicant_gid": r[4], "reviewer_gid": r[5], "status": r[6],
            "source_ref": r[7], "share_scope": r[8], "created_at": str(r[9]), "updated_at": str(r[10])
        }
        for r in rows
    ]}


@router.post("/orders", status_code=201)
def create_order(body: CreateOrderBody, current_user: dict = Depends(_SUBMIT)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_proj_approval_orders "
                "(gid, title, order_type, project_gid, applicant_gid, reviewer_gid, source_ref, content) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, body.title, body.order_type, body.project_gid,
                 current_user["gid"], body.reviewer_gid, body.source_ref,
                 json.dumps(body.content, ensure_ascii=False))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.get("/orders/{gid}")
def get_order(gid: str, current_user: dict = Depends(_SUBMIT)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, project_gid, order_type, title, applicant_gid, "
                "reviewer_gid, status, source_ref, content, opinions, meta, created_at, updated_at "
                "FROM workmanship_proj_approval_orders WHERE gid = %s",
                (gid,)
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="审批单不存在")
    return {"success": True, "data": {
        "gid": row[0], "project_gid": row[1], "order_type": row[2], "title": row[3],
        "applicant_gid": row[4], "reviewer_gid": row[5], "status": row[6],
        "source_ref": row[7], "content": row[8], "opinions": row[9], "meta": row[10],
        "created_at": str(row[11]), "updated_at": str(row[12])
    }}


def _append_opinion(conn, gid: str, actor_gid: str, action: str, comment: str):
    opinion = {"actor_gid": actor_gid, "action": action, "comment": comment}
    conn.cursor().execute(
        "UPDATE workmanship_proj_approval_orders SET opinions = opinions || %s, updated_at = NOW() "
        "WHERE gid = %s",
        (json.dumps([opinion], ensure_ascii=False), gid)
    )


@router.post("/orders/{gid}/start")
def start_review(gid: str, current_user: dict = Depends(_SUBMIT)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_approval_orders SET status = 'in_review', updated_at = NOW() "
                "WHERE gid = %s AND status = 'pending' AND applicant_gid = %s",
                (gid, current_user["gid"])
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="无法提交审批（状态或权限不符）")
        _append_opinion(conn, gid, current_user["gid"], "submit", "提交审批")
        conn.commit()
    return {"success": True}


@router.post("/orders/{gid}/approve")
def approve_order(gid: str, body: OpinionBody, current_user: dict = Depends(_APPROVE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_approval_orders SET status = 'approved', updated_at = NOW() "
                "WHERE gid = %s AND status = 'in_review'",
                (gid,)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="审批单状态不符")
            # 读取审批单内容，用于后续钩子
            cur.execute(
                "SELECT order_type, content, applicant_gid FROM workmanship_proj_approval_orders WHERE gid = %s",
                (gid,)
            )
            row = cur.fetchone()
        _append_opinion(conn, gid, current_user["gid"], "approve", body.comment)

        # ── scope_upgrade 钩子 ────────────────────────────────────
        if row and row[0] == "scope_upgrade":
            item = row[1] or {}
            if isinstance(item, dict):
                _apply_scope_upgrade(conn, item.get("item_type", ""),
                                     item.get("item_gid", ""),
                                     item.get("target_scope", ""))
            # 通知申请人
            try:
                from backend.platform_sdk.notifications import create_notification
                create_notification(
                    conn,
                    user_gid=row[2],
                    type_="scope_approved",
                    item_type=item.get("item_type"),
                    item_gid=item.get("item_gid"),
                    title=f"范围提升已通过：{item.get('item_title','')}",
                    body=f"已提升至 {item.get('target_scope','')}",
                )
            except Exception:
                _log.warning("approve_order: 发送 scope_approved 通知失败", exc_info=True)
def reject_order(gid: str, body: OpinionBody, current_user: dict = Depends(_APPROVE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_approval_orders SET status = 'rejected', updated_at = NOW() "
                "WHERE gid = %s AND status = 'in_review'",
                (gid,)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="审批单状态不符")
            cur.execute(
                "SELECT order_type, content, applicant_gid FROM workmanship_proj_approval_orders WHERE gid = %s",
                (gid,)
            )
            row = cur.fetchone()
        _append_opinion(conn, gid, current_user["gid"], "reject", body.comment)

        # ── scope_upgrade 驳回通知 ────────────────────────────────
        if row and row[0] == "scope_upgrade":
            item = row[1] or {}
            try:
                from backend.platform_sdk.notifications import create_notification
                create_notification(
                    conn,
                    user_gid=row[2],
                    type_="scope_rejected",
                    item_type=item.get("item_type") if isinstance(item, dict) else None,
                    item_gid=item.get("item_gid") if isinstance(item, dict) else None,
                    title=f"范围提升已驳回：{item.get('item_title','') if isinstance(item, dict) else ''}",
                    body=body.comment,
                )
            except Exception:
                _log.warning("reject_order: 发送 scope_rejected 通知失败", exc_info=True)

        conn.commit()
    return {"success": True}


@router.post("/orders/{gid}/withdraw")
def withdraw_order(gid: str, current_user: dict = Depends(_SUBMIT)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_approval_orders SET status = 'withdrawn', updated_at = NOW() "
                "WHERE gid = %s AND applicant_gid = %s AND status IN ('pending','in_review')",
                (gid, current_user["gid"])
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="无法撤回（状态或权限不符）")
        _append_opinion(conn, gid, current_user["gid"], "withdraw", "已撤回")
        conn.commit()
    return {"success": True}


# ── 范围提升审批 ───────────────────────────────────────────────────

_SCOPE_ORDER = ["local", "project", "team", "global"]

# 每个目标范围需要的审批角色
_SCOPE_REVIEWER_ROLE = {
    "project": "project_admin",
    "team":    "team_admin",
    "global":  "super_admin",
}

# 每个 item_type 对应的 PG 表名
_ITEM_TABLE = {
    "project":   "workmanship_proj_projects",
    "std_op":    "workmanship_tpl_gbop_entries",
    "approval":  "workmanship_proj_approval_orders",
}


def _apply_scope_upgrade(conn, item_type: str, item_gid: str, target_scope: str):
    """审批通过后，更新目标表的 share_scope 字段"""
    table = _ITEM_TABLE.get(item_type)
    if not table:
        return  # 本地 SQLite 表暂不在云端更新
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET share_scope = %s WHERE gid = %s",
            (target_scope, item_gid)
        )


@router.post("/orders/scope_upgrade", status_code=201)
def create_scope_upgrade_order(body: ScopeUpgradeBody, current_user: dict = Depends(_SUBMIT)):
    """申请将某条数据的 share_scope 提升至更高级别"""
    if body.target_scope not in _SCOPE_ORDER:
        raise HTTPException(status_code=400, detail=f"无效的目标范围: {body.target_scope}")
    if _SCOPE_ORDER.index(body.target_scope) <= _SCOPE_ORDER.index(body.current_scope):
        raise HTTPException(status_code=400, detail="目标范围必须高于当前范围")

    reviewer_role = _SCOPE_REVIEWER_ROLE.get(body.target_scope)
    if not reviewer_role:
        raise HTTPException(status_code=400, detail=f"无法升至范围: {body.target_scope}")

    gid = str(next_gid())
    content = {
        "item_type":     body.item_type,
        "item_gid":      body.item_gid,
        "item_title":    body.item_title,
        "current_scope": body.current_scope,
        "target_scope":  body.target_scope,
        "reason":        body.reason,
    }
    title = f"范围提升申请：{body.item_title}（{body.current_scope} → {body.target_scope}）"

    with get_conn() as conn:
        reviewer_gid = find_active_user_by_role(reviewer_role, current_user.get("team_id"))
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_proj_approval_orders "
                "(gid, title, order_type, applicant_gid, reviewer_gid, content) "
                "VALUES (%s, %s, 'scope_upgrade', %s, %s, %s)",
                (gid, title, current_user["gid"], reviewer_gid,
                 json.dumps(content, ensure_ascii=False))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "reviewer_gid": reviewer_gid}}
