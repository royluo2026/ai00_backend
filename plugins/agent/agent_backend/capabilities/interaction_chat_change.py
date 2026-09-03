"""Governed Agent chat and confirmation interaction boundary."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.contracts import BusinessInvariantContract, CorrelationRef, ExposurePolicy, ResourceSelector
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec, CapabilityStreamOutput

OPERATIONS = ("chat_stream", "chat_sync", "confirm", "confirm_sync")
CHAT_OPERATIONS = ("chat_stream", "chat_sync")


async def _collect_v1(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    iterator = getattr(value, "body_iterator", None)
    if iterator is None:
        return {"data": value}
    chunks: list[str] = []
    async for chunk in iterator:
        chunks.append(chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
    return {"events": chunks, "media_type": getattr(value, "media_type", "text/event-stream")}


async def _collect_v2(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if value.get("error"):
            raise CapabilityBusinessError(
                "provider_unavailable", str(value["error"]), retryable=True,
            )
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 1_048_576:
            raise ValueError("synchronous response exceeds 1048576 characters")
        return {"response_json": encoded}
    iterator = getattr(value, "body_iterator", None)
    if iterator is None:
        raise ValueError("unsupported Agent response type")
    media_type = getattr(value, "media_type", "text/event-stream")
    return CapabilityStreamOutput(
        iterator=iterator,
        output={"data": {"media_type": media_type}},
        media_type=media_type,
    )


def _v2_body(raw_body: Any) -> dict[str, Any]:
    if not isinstance(raw_body, dict):
        raise ValueError("body must be an object")
    body = dict(raw_body)
    context_json = body.pop("context_json", "")
    if context_json:
        context = json.loads(context_json)
        if not isinstance(context, dict):
            raise ValueError("context_json must encode an object")
        body["context"] = context
    return body


async def _apply_interaction_chat_change(
    payload: dict[str, Any], context: CapabilityContext, *, version: int,
) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    allowed = CHAT_OPERATIONS if version == 2 else OPERATIONS
    if operation not in allowed:
        raise ValueError(f"operation must be one of: {', '.join(allowed)}")
    from ..routers import ai_chat as legacy
    body = payload.get("body")
    if not isinstance(body, dict):
        raise ValueError("body must be an object")
    if version == 2:
        body = _v2_body(body)
    domain_client = getattr(context, "domain_client", None)
    identity = getattr(context, "effective_identity", None)
    catalog_runtime = None
    if domain_client is not None and identity is not None:
        from ..ai_assistant.catalog_tools import CatalogToolRegistry
        import uuid
        tool_registry = CatalogToolRegistry(domain_client.catalog(), client=domain_client)
        agent_run_id = f"xiaorou-{uuid.uuid4().hex}"
        catalog_runtime = {
            "registry": tool_registry,
            "identity_factory": lambda session_gid, tool, inputs: domain_client.issue_agent_run_identity(
                identity,
                agent_run_id=agent_run_id,
                session_gid=session_gid,
                capability_scopes=(tool.capability_id,),
                resource_scopes=tool.resource_scopes(inputs),
            ),
            "correlation": CorrelationRef(
                request_id=context.request_id or f"agent_chat_{context.user_gid}",
                trace_id=context.request_id or None,
            ),
            "catalog_release": domain_client.catalog_release,
        }
    user = {"gid": context.user_gid, "_catalog_runtime": catalog_runtime}
    token = str(payload.get("ai00_token") or "")
    collector = _collect_v2 if version == 2 else _collect_v1
    if operation == "chat_stream":
        collected = await collector(legacy._legacy_chat_stream(body, user, token))
        return collected if isinstance(collected, CapabilityStreamOutput) else {"data": collected}
    if operation == "chat_sync":
        return {"data": await collector(legacy._legacy_chat_sync(body, user, token))}
    if operation == "confirm":
        return {"data": await collector(legacy._legacy_confirm_tool(body, user))}
    return {"data": await collector(legacy._legacy_confirm_tool_sync(body, user))}


async def apply_interaction_chat_change_v1(
    payload: dict[str, Any], context: CapabilityContext,
) -> dict[str, Any]:
    return await _apply_interaction_chat_change(payload, context, version=1)


async def apply_interaction_chat_change(
    payload: dict[str, Any], context: CapabilityContext,
) -> dict[str, Any]:
    return await _apply_interaction_chat_change(payload, context, version=2)


def register_interaction_chat_change_capability(registry: Any) -> None:
    v1 = CapabilitySpec(
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
    v2 = CapabilitySpec(
        id="agent.interaction.chat.change.apply", version=2, owner="agent",
        description="Execute governed Agent chat and confirmation interactions with bounded event projection.",
        use_when="A governed Agent consumer sends a chat turn or confirms a pending tool interaction.",
        do_not_use_when="The request only cancels an interaction or manages Agent sessions directly.",
        risk="write", confirmation="none", idempotent=False, permissions=("agent.interact",),
        input_schema={"type": "object", "required": ["operation", "body"], "properties": {
            "operation": {"type": "string", "enum": list(CHAT_OPERATIONS)},
            "body": {"type": "object", "properties": {
                "message": {"type": "string"},
                "session_id": {"type": ["string", "null"]},
                "session_gid": {"type": ["string", "null"]},
                "confirm_token": {"type": "string"},
                "tool_name": {"type": "string"},
                "tool_use_id": {"type": "string"},
                "auth_token": {"type": "string"},
                "context_json": {"type": "string", "maxLength": 65_536},
            }, "additionalProperties": False},
            "ai00_token": {"type": "string"},
        }, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {
            "data": {"type": "object", "properties": {
                "stream_id": {"type": "string", "pattern": "^capability-stream-[0-9a-f]{32}$"},
                "media_type": {"type": "string"},
                "response_json": {"type": "string", "maxLength": 1_048_576},
            }, "additionalProperties": False},
        }, "additionalProperties": False},
        tags=("agent", "interaction", "chat", "write"),
    )
    from .provider import descriptor_for
    v1_governed = v1.model_copy(update={"plugin_callable": True})
    registry.register(
        v1_governed,
        apply_interaction_chat_change_v1,
        descriptor=descriptor_for(v1_governed).model_copy(update={
            "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=False, mcp=False),
        }),
    )
    v2_governed = v2.model_copy(update={"plugin_callable": True})
    v2_descriptor = descriptor_for(v2_governed).model_copy(update={
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=False, mcp=False),
        "consistency_policy": "eventual",
        "evidence_policy": "optional",
        "resource_selectors": (
            ResourceSelector(
                resource_type="agent-session", payload_path="body.session_id", required=False,
            ),
            ResourceSelector(
                resource_type="agent-session", payload_path="body.session_gid", required=False,
            ),
        ),
        "business_effect": (
            "Authenticated internal users can continue their own Xiaorou conversations while "
            "downstream tool writes remain governed by their owning capabilities."
        ),
        "business_acceptance_criteria": (
            "Each accepted request executes as the authenticated actor and never as a caller-supplied user identity.",
            "A supplied chat session is used only when it belongs to the authenticated actor.",
            "The caller receives a schema-valid bounded synchronous result or a single-use stream channel capped at 500 events.",
        ),
        "business_invariants": (
            BusinessInvariantContract(
                rule_id="agent.interaction.chat.actor_bound",
                version=1,
                statement="Every chat interaction executes as the authenticated Gateway actor.",
                applies_when="an Agent chat request is accepted",
                enforcement_ref="plugins/agent/agent_backend/routers/ai_chat.py:_normalize_interaction_payload",
                error_code="permission_denied",
                test_refs=(
                    "backend/tests/test_agent_interaction_chat_change_boundary.py::test_web_chat_pins_v2_and_normalizes_trusted_payload",
                ),
            ),
            BusinessInvariantContract(
                rule_id="agent.interaction.chat.session_owned",
                version=1,
                statement="A supplied chat session can be continued or confirmed only by its authenticated owner.",
                applies_when="the request supplies a session identifier",
                enforcement_ref="plugins/agent/agent_backend/routers/ai_chat.py:_require_legacy_session_owner",
                error_code="resource_not_found",
                test_refs=(
                    "backend/tests/test_agent_interaction_chat_change_boundary.py::test_agent_chat_rejects_a_foreign_session",
                ),
            ),
        ),
        "no_business_invariant_reason": None,
    })
    registry.register(v2_governed, apply_interaction_chat_change, descriptor=v2_descriptor)


__all__ = [
    "OPERATIONS",
    "apply_interaction_chat_change",
    "apply_interaction_chat_change_v1",
    "register_interaction_chat_change_capability",
]
