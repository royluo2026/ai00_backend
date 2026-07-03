"""
backend/ai_assistant/pause_store.py
────────────────────────────────────
Canvas 执行暂停状态内存存储。
用于 human/human_approval/human_task 节点的暂停-确认-恢复流程。
"""
from __future__ import annotations
import secrets
import time

# { pause_token: {...} }
_PAUSED: dict[str, dict] = {}

# 暂停状态最长保留 1 小时（用户长时间未确认则过期）
_TTL = 3600.0


def save_pause(
    canvas_data:     dict,
    prev_results:    dict,
    halted_node_id:  str,
    halted_label:    str,
    owner_gid:       str,
    auth_mode:       str,
    auth_token:      str,
    context_summary: list | None = None,
) -> str:
    """保存暂停状态，返回 pause_token（16字节随机 hex）。"""
    token = secrets.token_hex(16)
    _PAUSED[token] = {
        "canvas_data":      canvas_data,
        "prev_results":     prev_results,
        "halted_node_id":   halted_node_id,
        "halted_label":     halted_label,
        "owner_gid":        owner_gid,
        "auth_mode":        auth_mode,
        "auth_token":       auth_token,
        "context_summary":  context_summary or [],
        "created_at":       time.monotonic(),
    }
    return token


def load_pause(token: str) -> dict | None:
    """加载暂停状态。过期或不存在返回 None。"""
    entry = _PAUSED.get(token)
    if not entry:
        return None
    if time.monotonic() - entry["created_at"] > _TTL:
        _PAUSED.pop(token, None)
        return None
    return entry


def clear_pause(token: str) -> None:
    """清除暂停状态（执行完成或被用户拒绝后调用）。"""
    _PAUSED.pop(token, None)
