"""
Project Management follower notification trigger.
─────────────────────────────────
关注条件触发 → 写通知

调用方式：
    from backend.utils.follow_trigger import notify_followers
    notify_followers(conn, 'issue', item_gid, item_title,
                     events=['status_change', 'resolved'],
                     actor_user_gid=current_user_gid)
"""
from __future__ import annotations

import json
import logging

from .public import publish_notification

logger = logging.getLogger(__name__)

# 所有合法的订阅条件键
VALID_CONDITIONS = {
    "any_change", "status_change", "comment_added",
    "resolved", "assigned_to_me", "mentioned",
}

# 终止状态：认定为 "resolved"
RESOLVED_STATUSES = {"resolved", "closed", "done", "completed", "6/6"}


def _parse_notify_on(raw) -> list[str]:
    """将数据库里的 notify_on 值（TEXT 或 JSONB）解析为列表。"""
    if isinstance(raw, list):
        return [c for c in raw if c in VALID_CONDITIONS]
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                arr = json.loads(s)
                return [c for c in arr if c in VALID_CONDITIONS]
            except Exception:
                pass
        # 旧式单值字符串 → 降级映射
        if s in ("all", "any_change"):
            return ["any_change"]
        if s in ("key_changes",):
            return ["status_change", "resolved", "assigned_to_me"]
        if s == "none":
            return []
        return [s] if s in VALID_CONDITIONS else []
    return []


def notify_followers(
    conn,
    item_type: str,
    item_gid: str,
    item_title: str,
    events: list[str],
    actor_user_gid: str | None = None,
) -> int:
    """
    查询所有关注 (item_type, item_gid) 的用户，
    对每个用户检查其 notify_on 条件与 events 的交集，命中则写一条通知。

    返回写入的通知数量。
    """
    if not events:
        return 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, user_gid, notify_on FROM workmanship_work_follows "
                "WHERE item_type = %s AND item_gid = %s",
                (item_type, item_gid),
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.warning(f"[follow_trigger] 查询关注列表失败: {e}")
        return 0

    count = 0
    for row in rows:
        follow_user_gid = row["user_gid"]
        # 不给触发者自己发通知
        if actor_user_gid and follow_user_gid == actor_user_gid:
            continue

        conditions = _parse_notify_on(row["notify_on"])
        if not conditions:
            continue

        # 检查是否命中
        hit = any(c in events for c in conditions)
        if not hit:
            continue

        # 构建通知文案
        event_label = _events_label(events)
        try:
            gid = publish_notification(
                user_gid=follow_user_gid, type_="item_status", item_type=item_type,
                item_gid=item_gid, title=f"{_item_label(item_type)}更新：{item_title}", body=event_label,
            )
            if gid:
                count += 1
        except Exception as e:
            logger.warning(f"[follow_trigger] 写通知失败 user={follow_user_gid}: {e}")

    return count


def _item_label(item_type: str) -> str:
    return {"task": "任务", "issue": "问题", "project": "项目"}.get(item_type, "条目")


def _events_label(events: list[str]) -> str:
    labels = {
        "any_change":     "内容已更新",
        "status_change":  "状态已变更",
        "comment_added":  "有新评论",
        "resolved":       "已解决/关闭",
        "assigned_to_me": "被指派给你",
        "mentioned":      "你在评论中被@",
    }
    parts = [labels[e] for e in events if e in labels]
    return "、".join(parts) if parts else "已更新"
