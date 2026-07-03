"""
backend/ai_assistant/tool_handlers/file_tools.py
─────────────────────────────────────────────────
文件读写工具处理器
（云端版不直接操作本地文件，通过附件接口访问 PG 存储的文件元数据）
"""
from __future__ import annotations
from typing import Any

TOOL_NAMES: set[str] = {
    "read_file",
    "write_local_file",
    "read_local_md",
}


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    **_kwargs,
) -> Any:
    if tool_name == "read_local_md":
        return _read_local_md(inputs.get("path", ""))
    if tool_name in ("read_file", "write_local_file"):
        return {
            "error": "云端模式不支持本地文件读写，请使用附件上传接口。",
            "tool":  tool_name,
        }
    return {"error": f"file_tools: 未知工具 {tool_name}"}


def _read_local_md(path: str) -> dict:
    """云端版：直接返回提示，不读本地文件。"""
    return {
        "error": f"云端模式无法读取本地文件：{path}",
        "hint":  "请将文件上传到附件系统后再引用。",
    }
