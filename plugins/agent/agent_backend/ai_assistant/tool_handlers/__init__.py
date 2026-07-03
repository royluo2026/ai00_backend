"""
backend/ai_assistant/tool_handlers/__init__.py
───────────────────────────────────────────────
工具包分发入口。

每个子模块暴露：
  TOOL_NAMES: set[str]                               — 该模块负责的工具名
  dispatch(tool_name, inputs, auth_mode, auth_token, user_gid, session_gid) -> dict
"""
from __future__ import annotations
from typing import Any


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    user_gid: str = "",
    session_gid: str = "",
    is_confirmed: bool = False,
    canvas_context: dict | None = None,
) -> Any:
    """主分发入口：按工具名路由到对应 handler 模块。"""
    from . import (
        project_tools,
        knowledge_tools,
        craft_tools,
        skill_tools,
        system_tools,
        feishu_tools,
        file_tools,
        memory_tools,
    )

    kwargs = dict(
        auth_mode=auth_mode,
        auth_token=auth_token,
        user_gid=user_gid,
        session_gid=session_gid,
        canvas_context=canvas_context,
    )

    for handler in (
        project_tools,
        knowledge_tools,
        craft_tools,
        skill_tools,
        system_tools,
        feishu_tools,
        file_tools,
        memory_tools,
    ):
        if tool_name in handler.TOOL_NAMES:
            result = handler.dispatch(tool_name, inputs, **kwargs)
            # 低置信度包装：confidence < 0.6 时追加 _low_confidence 标记
            if isinstance(result, dict) and result.get("confidence", 1.0) < 0.6:
                result["_low_confidence"] = True
            return result

    # skill_tool_<name> 前缀 → skill_tools 兜底
    if tool_name.startswith("skill_tool_"):
        return skill_tools.dispatch(tool_name, inputs, **kwargs)

    return {"error": f"未知工具：{tool_name}"}
