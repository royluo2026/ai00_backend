"""
backend/ai_assistant/tool_executor.py
──────────────────────────────────────
工具执行器：分发工具调用，管理写操作确认令牌。
"""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ..data.confirmation_repository import SqlConfirmationRepository

# ── 确认令牌（5 分钟 TTL，Agent DB 持久化 + CAS）─────────────────────────────
_CONFIRM_STORE = SqlConfirmationRepository()
_TOKEN_TTL = 300  # seconds


def configure_confirmation_store(store) -> None:
    global _CONFIRM_STORE
    _CONFIRM_STORE = store


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _payload_hash(inputs: dict) -> str:
    encoded = json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def issue_confirm_token(
    tool_name: str, inputs: dict, session_gid: str, user_gid: str, *,
    catalog_release: str = "", capability_id: str = "", major_version: int = 1,
    idempotency_key: str = "", agent_identity: Any = None,
) -> str:
    token = str(uuid.uuid4())
    identity_json = (
        agent_identity.model_dump(mode="json")
        if hasattr(agent_identity, "model_dump")
        else dict(vars(agent_identity)) if hasattr(agent_identity, "__dict__")
        else dict(agent_identity or {})
    )
    _CONFIRM_STORE.save(_token_hash(token), {
        "tool_name": tool_name, "inputs": dict(inputs), "session_gid": session_gid,
        "user_gid": user_gid, "expires_at": datetime.now(UTC) + timedelta(seconds=_TOKEN_TTL),
        "catalog_release": catalog_release, "capability_id": capability_id,
        "major_version": major_version, "payload_hash": _payload_hash(inputs),
        "idempotency_key": idempotency_key or f"agent-tool-{token}",
        "agent_identity": identity_json, "state": "pending",
    })
    return token


def begin_confirm_token(
    token: str, tool_name: str, session_gid: str, user_gid: str, *,
    catalog_release: str = "", capability_id: str = "", major_version: int = 1,
) -> tuple[bool, dict]:
    """Atomically reserve a fully-bound pending confirmation."""
    expected = {
        "tool_name": tool_name, "session_gid": session_gid, "user_gid": user_gid,
        "major_version": major_version,
    }
    if catalog_release:
        expected["catalog_release"] = catalog_release
    if capability_id:
        expected["capability_id"] = capability_id
    pending = _CONFIRM_STORE.begin(_token_hash(token), expected)
    if not pending or pending.get("payload_hash") != _payload_hash(pending.get("inputs") or {}):
        if pending:
            _CONFIRM_STORE.finish(_token_hash(token), accepted=False)
        return False, {}
    return True, pending


def finish_confirm_token(token: str, *, accepted: bool) -> None:
    """Consume an accepted token or release a failed invocation for retry."""
    _CONFIRM_STORE.finish(_token_hash(token), accepted=accepted)


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
