"""
backend/routers/mentions.py
──────────────────────────────
@mention 通知 API

端点：
  POST /api/mentions/notify  → 向被@的用户发送站内通知
"""
import logging
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.notif import create_notification

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mentions"])


class MentionNotifyBody(BaseModel):
    item_type: str                    # task | issue | project | ...
    item_gid: str                     # 云端 gid
    item_title: str = ""
    mentioned_gids: List[str]         # 被@的用户 gid 列表
    context: str = ""                 # @出现位置的文字片段（用于通知 body）
    notify: bool = True               # 是否实际发通知（前端开关）
    is_important: bool = False        # 重要标记（预留，后期触发飞书消息）


@router.post("/api/mentions/notify")
def send_mention_notifications(
    body: MentionNotifyBody,
    current_user: dict = Depends(get_current_user),
):
    """
    向所有被@的用户写站内通知。
    - notify=False 时静默跳过（用于仅保存不提醒的场景）
    - 不给自己发通知
    - is_important 目前仅记录，后续接飞书消息推送
    """
    if not body.notify or not body.mentioned_gids:
        return {"success": True, "data": {"sent": 0}}

    sender_name = current_user.get("name") or "某人"
    body_text = (body.context[:150] + "…") if len(body.context) > 150 else body.context

    count = 0
    with get_conn() as conn:
        for gid in set(body.mentioned_gids):
            if gid == current_user["gid"]:
                continue
            try:
                notif_gid = create_notification(
                    conn,
                    user_gid=gid,
                    type_="mentioned",
                    item_type=body.item_type,
                    item_gid=body.item_gid,
                    title=f"{sender_name} 在「{body.item_title}」中 @了你",
                    body=body_text,
                )
                if notif_gid:
                    count += 1
                    if body.is_important:
                        # 预留：重要标记 → 飞书消息推送（best-effort，不影响主流程）
                        _try_feishu_important(conn, gid, sender_name, body)
            except Exception as e:
                logger.warning(f"[mentions] 通知写入失败 user={gid}: {e}")

    return {"success": True, "data": {"sent": count}}


def _try_feishu_important(conn, user_gid: str, sender_name: str, body: MentionNotifyBody):
    """向飞书用户发送重要@通知消息（后续实现，当前为占位）。"""
    pass
