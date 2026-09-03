"""
backend/ai_assistant/tool_executor.py
──────────────────────────────────────
工具执行器：分发工具调用，管理写操作确认令牌。
"""
from __future__ import annotations
import hashlib
import json
import time
import uuid
from threading import Lock
from typing import Any

# ── 确认令牌（5 分钟 TTL，内存存储，单进程 OK）────────────────────────────────
_CONFIRM_TOKENS: dict[str, dict] = {}
_CONFIRM_TOKENS_LOCK = Lock()
_TOKEN_TTL = 300  # seconds


def _payload_hash(inputs: dict) -> str:
    encoded = json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def issue_confirm_token(
    tool_name: str, inputs: dict, session_gid: str, user_gid: str, *,
    catalog_release: str = "", capability_id: str = "", major_version: int = 1,
) -> str:
    token = str(uuid.uuid4())
    with _CONFIRM_TOKENS_LOCK:
        _CONFIRM_TOKENS[token] = {
            "tool_name": tool_name, "inputs": inputs, "session_gid": session_gid,
            "user_gid": user_gid, "expires_at": time.time() + _TOKEN_TTL,
            "catalog_release": catalog_release, "capability_id": capability_id,
            "major_version": major_version, "payload_hash": _payload_hash(inputs),
            "state": "pending",
        }
    return token


def begin_confirm_token(
    token: str, tool_name: str, session_gid: str, user_gid: str, *,
    catalog_release: str = "", capability_id: str = "", major_version: int = 1,
) -> tuple[bool, dict]:
    """Atomically reserve a fully-bound pending confirmation."""
    with _CONFIRM_TOKENS_LOCK:
        pending = _CONFIRM_TOKENS.get(token)
        if not pending:
            return False, {}
        if time.time() > pending["expires_at"]:
            _CONFIRM_TOKENS.pop(token, None)
            return False, {}
        if pending["tool_name"] != tool_name:
            return False, {}
        if pending["session_gid"] != session_gid or pending["user_gid"] != user_gid:
            return False, {}
        if pending["state"] != "pending":
            return False, {}
        if pending["payload_hash"] != _payload_hash(pending["inputs"]):
            return False, {}
        if catalog_release and pending["catalog_release"] != catalog_release:
            return False, {}
        if capability_id and pending["capability_id"] != capability_id:
            return False, {}
        if pending["major_version"] != major_version:
            return False, {}
        pending["state"] = "inflight"
        return True, dict(pending)


def finish_confirm_token(token: str, *, accepted: bool) -> None:
    """Consume an accepted token or release a failed invocation for retry."""
    with _CONFIRM_TOKENS_LOCK:
        pending = _CONFIRM_TOKENS.get(token)
        if not pending or pending.get("state") != "inflight":
            return
        if accepted:
            _CONFIRM_TOKENS.pop(token, None)
        else:
            pending["state"] = "pending"


def consume_confirm_token(token: str, tool_name: str, session_gid: str, user_gid: str) -> tuple[bool, dict]:
    """Compatibility atomic consume for non-Gateway callers."""
    valid, pending = begin_confirm_token(token, tool_name, session_gid, user_gid)
    if valid:
        finish_confirm_token(token, accepted=True)
    return valid, pending


def build_preview(tool_name: str, inputs: dict) -> str:
    """生成写操作人类可读预览。"""
    if tool_name == "create_task":
        return f"创建任务：{inputs.get('title', '(无标题)')} [优先级: {inputs.get('priority', 'normal')}]"
    if tool_name == "update_task":
        parts = [f"GID={inputs.get('gid', '?')}"]
        for k, v in inputs.items():
            if k != "gid":
                parts.append(f"{k}={v}")
        return f"更新任务：{', '.join(parts)}"
    if tool_name == "create_issue":
        return f"创建问题：{inputs.get('title', '(无标题)')} [严重度: {inputs.get('severity', 'medium')}]"
    if tool_name == "update_issue":
        parts = [f"GID={inputs.get('gid', '?')}"]
        for k, v in inputs.items():
            if k != "gid":
                parts.append(f"{k}={v}")
        return f"更新问题：{', '.join(parts)}"
    if tool_name == "create_approval_order":
        return f"创建审批单：{inputs.get('title', '(无标题)')}"
    return f"执行：{tool_name}({inputs})"


def execute_tool(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    user_gid: str = "",
    session_gid: str = "",
    is_confirmed: bool = False,
    canvas_context: dict | None = None,
) -> dict[str, Any]:
    """分发工具调用。返回结果 dict，失败时含 error 字段。"""
    return {
        "error": "legacy Agent tool execution is retired; use a Catalog-generated tool through the Capability Gateway",
        "tool": tool_name,
    }


async def execute_catalog_tool(
    registry, tool_name: str, inputs: dict, *, identity, correlation,
    idempotency_key: str | None = None,
):
    """Execute only a stored Catalog reverse mapping through DomainCapabilityClient."""
    return await registry.execute(
        tool_name, inputs, identity=identity, correlation=correlation,
        idempotency_key=idempotency_key,
    )
