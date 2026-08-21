"""Governed Agent chat and confirmation interaction boundary."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

OPERATIONS = ("chat_stream", "chat_sync", "confirm", "confirm_sync")


async def _collect(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    iterator = getattr(value, "body_iterator", None)
    if iterator is None:
        return {"data": value}
    chunks: list[str] = []
    async for chunk in iterator:
        chunks.append(chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
    return {"events": chunks, "media_type": getattr(value, "media_type", "text/event-stream")}


async def apply_interaction_chat_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    from ..routers import ai_chat as legacy
    body = payload.get("body")
    if not isinstance(body, dict):
        raise ValueError("body must be an object")
    user = {"gid": context.user_gid}
    token = str(payload.get("ai00_token") or "")
    if operation == "chat_stream":
        return {"data": await _collect(legacy._legacy_chat_stream(body, user, token))}
    if operation == "chat_sync":
        return {"data": await _collect(legacy._legacy_chat_sync(body, user, token))}
    if operation == "confirm":
        return {"data": await _collect(legacy._legacy_confirm_tool(body, user))}
    return {"data": await _collect(legacy._legacy_confirm_tool_sync(body, user))}


def register_interaction_chat_change_capability(registry: Any) -> None:
    spec = CapabilitySpec(
        id="agent.interaction.chat.change.apply", owner="agent",
        description="Execute governed Agent chat and confirmation interactions with bounded event projection.",
        use_when="A governed Agent consumer sends a chat turn or confirms a pending tool interaction.",
        do_not_use_when="The request only cancels an interaction or manages Agent sessions directly.",
        risk="write", confirmation="user", idempotent=False, permissions=("agent.interact",),
        input_schema={"type": "object", "required": ["operation", "body"], "properties": {
            "operation": {"type": "string", "enum": list(OPERATIONS)},
            "body": {"type": "object", "properties": {"message": {"type": "string"}, "session_id": {"type": ["string", "null"]}, "session_gid": {"type": ["string", "null"]}, "confirm_token": {"type": "string"}, "tool_name": {"type": "string"}, "tool_use_id": {"type": "string"}, "auth_token": {"type": "string"}}, "additionalProperties": False},
            "ai00_token": {"type": "string"},
        }, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "properties": {"events": {"type": "array", "maxItems": 500, "items": {"type": "string"}}, "media_type": {"type": "string"}, "answer": {"type": "string"}, "session_id": {"type": "string"}}, "additionalProperties": False}}, "additionalProperties": False},
        tags=("agent", "interaction", "chat", "write"),
    )
    from .provider import descriptor_for
    governed = spec.model_copy(update={"plugin_callable": True})
    registry.register(governed, apply_interaction_chat_change, descriptor=descriptor_for(governed))


__all__ = ["OPERATIONS", "apply_interaction_chat_change", "register_interaction_chat_change_capability"]
