"""
backend/utils/notif.py
──────────────────────
通知创建工具函数。
"""
import json
import logging

from backend.utils.gid import next_gid

logger = logging.getLogger(__name__)

# 与 notifications.py NOTIF_TYPE_DEFAULTS 保持一致
_NOTIF_DEFAULTS: dict[str, bool] = {
    "scope_approved": True,
    "scope_rejected": True,
    "item_status":    True,
    "new_follower":   True,
    "mentioned":      True,
}


def _user_wants(conn, user_gid: str, type_: str) -> bool:
    """检查用户是否开启了该类型通知（读取 notification_prefs）。"""
    default = _NOTIF_DEFAULTS.get(type_, True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT notification_prefs FROM workmanship_auth_users WHERE gid = %s", (user_gid,)
            )
            row = cur.fetchone()
        if not row or not row["notification_prefs"]:
            return default
        prefs = row["notification_prefs"] if isinstance(row["notification_prefs"], dict) else json.loads(row["notification_prefs"])
        return bool(prefs.get(type_, default))
    except Exception:
        return default


def create_notification(conn, user_gid: str, type_: str,
                        item_type: str | None, item_gid: str | None,
                        title: str, body: str = "") -> str | None:
    """
    在 notifications 表中插入一条通知记录。
    若用户已关闭该类型通知，则静默跳过（返回 None）。
    conn: psycopg2 连接（调用方负责 commit）
    """
    if not _user_wants(conn, user_gid, type_):
        return None
    gid = str(next_gid())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO workmanship_work_notifications (gid, user_gid, type, item_type, item_gid, title, body) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (gid, user_gid, type_, item_type, item_gid, title, body)
        )
    return gid
