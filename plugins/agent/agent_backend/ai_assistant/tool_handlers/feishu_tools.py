"""
backend/ai_assistant/tool_handlers/feishu_tools.py
───────────────────────────────────────────────────
飞书相关工具处理器（飞书模式专用）
"""
from __future__ import annotations
from typing import Any

TOOL_NAMES: set[str] = {
    # 飞书工具暂无额外实现，留作扩展占位
    # "send_feishu_message",
    # "create_feishu_doc",
}


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    **_kwargs,
) -> Any:
    return {"error": f"feishu_tools: 未知工具 {tool_name}"}
