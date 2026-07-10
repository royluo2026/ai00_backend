"""
backend/routers/notifications.py
──────────────────────────────────
通知 API（notifications）

端点：
  GET   /api/notifications                  → 通知列表
  GET   /api/notifications/unread_count     → 未读数量（轮询专用）
  PATCH /api/notifications/{gid}/read       → 标记单条已读
  PATCH /api/notifications/read_all         → 全部标记已读
  GET   /api/notifications/prefs            → 读取通知偏好
  PATCH /api/notifications/prefs            → 更新通知偏好
"""
import json
import logging

from fastapi import APIRouter, Depends, Query

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# 通知类型默认偏好（true = 接收）
NOTIF_TYPE_DEFAULTS: dict[str, bool] = {
    "scope_approved": True,
    "scope_rejected": True,
    "item_status":    True,
    "new_follower":   True,
}


def _safe_prefs(raw) -> dict:
    """解析 JSONB 字段（可能是 str 或 dict），补全缺省值。"""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return {k: raw.get(k, v) for k, v in NOTIF_TYPE_DEFAULTS.items()}


def _row_get(row, key: str, idx: int = 0, default=None):
    """兼容 dict/tuple 两类游标返回结构。"""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[idx]
    except Exception:
        return default


# ── 通知列表 ──────────────────────────────────────────────────────────────────

@router.get("")
def list_notifications(
    unread_only: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                sql = (
                    "SELECT gid, type, item_type, item_gid, title, body, is_read, created_at "
                    "FROM workmanship_work_notifications WHERE user_gid = %s"
                    + (" AND is_read = FALSE" if unread_only else "")
                    + " ORDER BY created_at DESC LIMIT 100"
                )
                cur.execute(sql, (uid,))
                rows = cur.fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "gid": _row_get(r, "gid", 0, ""),
                    "type": _row_get(r, "type", 1, ""),
                    "item_type": _row_get(r, "item_type", 2, ""),
                    "item_gid": _row_get(r, "item_gid", 3, ""),
                    "title": _row_get(r, "title", 4, ""),
                    "body": _row_get(r, "body", 5, ""),
                    "is_read": bool(_row_get(r, "is_read", 6, False)),
                    "created_at": str(_row_get(r, "created_at", 7, "")),
                }
            )
        return {"success": True, "data": out}
    except Exception as e:
        logger.warning(f"[notifications] list failed: {e}")
        return {"success": True, "data": []}


# ── 未读数量（轮询专用，静默失败）─────────────────────────────────────────────

@router.get("/unread_count")
def unread_count(current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM workmanship_work_notifications WHERE user_gid = %s AND is_read = FALSE",
                    (uid,)
                )
                row = cur.fetchone()
                count = int(_row_get(row, "COUNT(*)", 0, 0) or 0)
        return {"success": True, "data": {"count": count}}
    except Exception as e:
        logger.warning(f"[notifications] unread_count failed: {e}")
        return {"success": True, "data": {"count": 0}}


# ── 通知偏好 GET / PATCH ──────────────────────────────────────────────────────
# 注意：这两个路由必须在 /{gid}/read 之前定义，防止 "prefs" 被当成 {gid}

@router.get("/prefs")
def get_prefs(current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT notification_prefs FROM workmanship_auth_users WHERE gid = %s", (uid,)
                )
                raw = cur.fetchone()
                raw = _row_get(raw, "notification_prefs", 0, {})
        return {"success": True, "data": _safe_prefs(raw)}
    except Exception as e:
        logger.warning(f"[notifications] get_prefs failed: {e}")
        return {"success": True, "data": _safe_prefs({})}


@router.patch("/prefs")
def update_prefs(body: dict, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 先读当前值再合并，防止覆盖未传字段
                cur.execute(
                    "SELECT notification_prefs FROM workmanship_auth_users WHERE gid = %s", (uid,)
                )
                row = cur.fetchone()
                current = _safe_prefs(_row_get(row, "notification_prefs", 0, {}))
                # 只允许修改已知类型的开关
                for k in NOTIF_TYPE_DEFAULTS:
                    if k in body:
                        current[k] = bool(body[k])
                cur.execute(
                    "UPDATE workmanship_auth_users SET notification_prefs = %s WHERE gid = %s",
                    (json.dumps(current), uid)
                )
            conn.commit()
        return {"success": True, "data": current}
    except Exception as e:
        logger.warning(f"[notifications] update_prefs failed: {e}")
        return {"success": False, "msg": str(e)}


# ── 全部标记已读 ──────────────────────────────────────────────────────────────

@router.patch("/read_all")
def read_all(current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_work_notifications SET is_read = TRUE WHERE user_gid = %s AND is_read = FALSE",
                    (uid,)
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"[notifications] read_all failed: {e}")
    return {"success": True}


# ── 标记单条已读 ──────────────────────────────────────────────────────────────

@router.patch("/{gid}/read")
def mark_read(gid: str, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_work_notifications SET is_read = TRUE WHERE gid = %s AND user_gid = %s",
                    (gid, uid)
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"[notifications] mark_read failed: {e}")
    return {"success": True}
