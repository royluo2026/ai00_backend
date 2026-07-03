"""
backend/routers/feishu_im.py
────────────────────────────
飞书 IM 集成 —— @我 消息查询
路由前缀：/api/feishu/im
权限：需要飞书登录（auth_mode == feishu），由 get_current_user 保证 JWT 有效
"""
import json
import logging
from fastapi import APIRouter, Depends, Query
from backend.routers.deps import get_current_user
from backend.services.feishu_service import FeishuService

router = APIRouter(prefix="/api/feishu/im", tags=["feishu_im"])
_svc = FeishuService()
_log = logging.getLogger(__name__)


@router.get("/mentions")
def get_my_mentions(
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """
    返回最近 @我 的飞书消息列表。
    优先用用户自己的 feishu token 遍历其所在的全部群聊（包括机器人未加入的群）；
    降级到机器人 tenant token（只能查机器人所在群）。
    """
    open_id = current_user.get("feishu_open_id", "")
    if not open_id:
        return {"items": [], "total": 0, "note": "当前用户未绑定飞书账号"}

    from backend.services import user_service as _us
    user_feishu_token = _us.get_feishu_token(current_user["gid"])

    results = []

    def _get_chats(chat_type: str) -> list:
        if user_feishu_token:
            try:
                return _svc.get_chats_as_user(user_feishu_token, chat_type=chat_type, page_size=50)
            except Exception:
                _log.warning("_get_chats: 用户 token 获取 %s 会话失败，降级到 bot", chat_type, exc_info=True)
        # 降级：机器人 token（仅 group）
        if chat_type == "group":
            try:
                return _svc.get_chats(page_size=50)
            except Exception:
                _log.warning("_get_chats: bot token 获取会话也失败", exc_info=True)
        return []

    def _get_messages(chat_id: str) -> list:
        if user_feishu_token:
            try:
                return _svc.get_chat_messages_as_user(chat_id, user_feishu_token, page_size=20)
            except Exception:
                _log.warning("_get_messages: 用户 token 获取消息失败 chat_id=%s，降级到 bot", chat_id, exc_info=True)
        try:
            return _svc.get_chat_messages(chat_id, page_size=20)
        except Exception:
            _log.warning("_get_messages: bot token 获取消息也失败 chat_id=%s", chat_id, exc_info=True)
            return []

    # 群聊 + 单聊 @mentions
    for chat_type in ("group", "p2p"):
        for chat in _get_chats(chat_type):
            chat_id   = chat.get("chat_id", "")
            chat_name = chat.get("name", "")
            for msg in _get_messages(chat_id):
                body_data = msg.get("body", {})
                mentions = _extract_mentions(body_data.get("content", "{}"))
                if open_id in mentions:
                    results.append({
                        "msg_id":     msg.get("message_id", ""),
                        "chat_id":    chat_id,
                        "chat_name":  chat_name,
                        "chat_type":  chat_type,
                        "sender":     msg.get("sender", {}).get("sender_id", {}).get("open_id", ""),
                        "sender_name": "",
                        "content":    _extract_text(body_data.get("content", "{}")),
                        "created_at": msg.get("create_time", ""),
                        "chat_link":  f"https://applink.feishu.cn/client/chat/open?openChatId={chat_id}",
                    })

    results.sort(key=lambda x: x["created_at"], reverse=True)
    return {"items": results[:limit], "total": len(results)}


def _extract_mentions(content_json: str) -> set:
    """从飞书消息 content JSON 提取被 @ 的 open_id 集合。"""
    try:
        data = json.loads(content_json)
        ids = set()
        for para in data.get("content", []):
            for elem in para:
                if elem.get("tag") == "at":
                    ids.add(elem.get("user_id", ""))
        return ids
    except Exception:
        _log.warning("_extract_mentions: 消息 content JSON 解析失败", exc_info=True)
        return set()


def _extract_text(content_json: str) -> str:
    """从飞书消息 content JSON 提取纯文本（最多 500 字）。"""
    try:
        data = json.loads(content_json)
        parts = []
        for para in data.get("content", []):
            for elem in para:
                if elem.get("tag") == "text":
                    parts.append(elem.get("text", ""))
                elif elem.get("tag") == "at":
                    parts.append(f"@{elem.get('user_name', '')}")
        return "".join(parts)[:500]
    except Exception:
        return content_json[:200]


@router.get("/contact-messages")
def get_contact_messages(
    name: str = "",
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """
    查询与指定飞书联系人（按姓名）相关的最近消息。
    优先用用户自己的 feishu token 遍历其所在的全部聊天（无需机器人在场）。
    """
    if not name:
        return {"error": "请提供 name 参数（联系人姓名）"}

    from backend.services import user_service as _us
    user_feishu_token = _us.get_feishu_token(current_user["gid"])

    # Step 1: 按姓名查找目标用户
    try:
        users = _svc.search_users_by_name(name, page_size=5)
    except Exception:
        users = []
    if not users:
        return {"items": [], "matched_users": [], "note": f"未找到名为「{name}」的飞书用户"}
    target = next((u for u in users if u["name"] == name), users[0])
    target_open_id = target["open_id"]

    def _get_chats_for_type(chat_type: str) -> list:
        if user_feishu_token:
            try:
                return _svc.get_chats_as_user(user_feishu_token, chat_type=chat_type, page_size=50)
            except Exception:
                pass
        if chat_type == "group":
            try:
                return _svc.get_chats(page_size=50)
            except Exception:
                pass
        if chat_type == "p2p":
            try:
                return _svc.get_p2p_chats(page_size=50)
            except Exception:
                pass
        return []

    def _get_msgs(chat_id: str) -> list:
        if user_feishu_token:
            try:
                return _svc.get_chat_messages_as_user(chat_id, user_feishu_token, page_size=20)
            except Exception:
                pass
        try:
            return _svc.get_chat_messages(chat_id, page_size=20)
        except Exception:
            return []

    # Step 2: 遍历群聊 + 单聊
    results = []
    for chat_type in ("group", "p2p"):
        for chat in _get_chats_for_type(chat_type):
            chat_id   = chat.get("chat_id", "")
            chat_name = chat.get("name", "") if chat_type == "group" else target["name"]
            for msg in _get_msgs(chat_id):
                sender_id = msg.get("sender", {}).get("sender_id", {}).get("open_id", "")
                if sender_id == target_open_id:
                    results.append({
                        "msg_id":      msg.get("message_id", ""),
                        "chat_id":     chat_id,
                        "chat_name":   chat_name,
                        "chat_type":   chat_type,
                        "sender_name": target["name"],
                        "content":     _extract_text(msg.get("body", {}).get("content", "{}")),
                        "created_at":  msg.get("create_time", ""),
                        "chat_link":   f"https://applink.feishu.cn/client/chat/open?openChatId={chat_id}",
                    })

    results.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "items":         results[:limit],
        "total":         len(results),
        "matched_users": users,
        "target":        target,
    }
