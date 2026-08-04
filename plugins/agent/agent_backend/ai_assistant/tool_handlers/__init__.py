"""Agent tool dispatch with Capability Kernel knowledge adapters."""
from __future__ import annotations
from typing import Any

def dispatch(tool_name: str, inputs: dict, auth_mode: str = "feishu", auth_token: str = "", user_gid: str = "", session_gid: str = "", is_confirmed: bool = False, canvas_context: dict | None = None) -> Any:
    if tool_name in {"search_knowledge", "get_knowledge_entry", "get_knowledge_document"}:
        from .capability_tools import dispatch_knowledge
        try:
            return dispatch_knowledge(tool_name, inputs, user_gid=user_gid, auth_mode=auth_mode)
        except Exception as exc:
            return {"error": str(exc), "tool": tool_name, "source": "capability"}
    from . import project_tools, knowledge_tools, craft_tools, skill_tools, system_tools, feishu_tools, file_tools, memory_tools
    kwargs = {"auth_mode": auth_mode, "auth_token": auth_token, "user_gid": user_gid, "session_gid": session_gid, "canvas_context": canvas_context}
    for handler in (project_tools, knowledge_tools, craft_tools, skill_tools, system_tools, feishu_tools, file_tools, memory_tools):
        if tool_name in handler.TOOL_NAMES:
            result = handler.dispatch(tool_name, inputs, **kwargs)
            if isinstance(result, dict) and result.get("confidence", 1.0) < 0.6: result["_low_confidence"] = True
            return result
    if tool_name.startswith("skill_tool_"): return skill_tools.dispatch(tool_name, inputs, **kwargs)
    return {"error": f"未知工具：{tool_name}"}
