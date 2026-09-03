"""User-confirmed execution boundary for Catalog-generated Agent tools."""
from __future__ import annotations

import json
import asyncio
from typing import Any

from backend.capability_v2.contracts import (
    BusinessInvariantContract, CorrelationRef, ExposurePolicy, ResourceSelector,
)
from backend.capability_v2.domain_client import DomainInvocation
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec


async def apply_catalog_tool_confirmation(
    payload: dict[str, Any], context: CapabilityContext,
) -> dict[str, Any]:
    from ..ai_assistant.catalog_tools import CatalogToolRegistry
    from ..ai_assistant import tool_executor
    from ..ai_assistant.session_store import _store

    client = context.domain_client
    identity = context.effective_identity
    session_gid = str(payload.get("session_gid") or "")
    tool_name = str(payload.get("tool_name") or "")
    token = str(payload.get("confirm_token") or "")
    _store.require_owned_session(session_gid, context.user_gid)
    registry = CatalogToolRegistry(client.catalog(), client=client)
    try:
        tool = registry.resolve(tool_name)
    except ValueError as exc:
        raise CapabilityBusinessError("invalid_input", str(exc)) from exc
    valid, pending = tool_executor.begin_confirm_token(
        token, tool_name, session_gid, context.user_gid,
        catalog_release=client.catalog_release,
        capability_id=tool.capability_id,
        major_version=tool.major_version,
    )
    if not valid:
        raise CapabilityBusinessError("invalid_input", "Agent confirmation token is invalid or expired")

    correlation = CorrelationRef(
        request_id=context.request_id or f"agent_confirm_{context.user_gid}",
        trace_id=context.request_id or None,
    )
    invocation = DomainInvocation(
        capability_id=tool.capability_id,
        major_version=tool.major_version,
        payload=dict(pending["inputs"]),
        idempotency_key=pending["idempotency_key"],
    )
    try:
        agent_identity_json = pending.get("agent_identity") or {}
        if not agent_identity_json:
            raise CapabilityBusinessError("invalid_input", "Agent run identity is missing")
        from backend.capability_v2.contracts import ConsumerIdentity
        identity = ConsumerIdentity.model_validate(agent_identity_json)
        result = await client._invoke_from_confirmed_parent(invocation, identity, correlation)
    except asyncio.CancelledError:
        tool_executor.finish_confirm_token(token, accepted=False)
        raise
    except Exception:
        tool_executor.finish_confirm_token(token, accepted=False)
        raise
    if not result.ok:
        tool_executor.finish_confirm_token(token, accepted=False)
        error = result.error
        raise CapabilityBusinessError(
            error.code if error else "provider_unavailable",
            error.message if error else "Catalog tool execution failed",
            retryable=bool(error and error.retryable),
            details=dict(error.details) if error else {},
        )
    tool_executor.finish_confirm_token(token, accepted=True)
    write_result = result.data.get("data", result.data) if isinstance(result.data, dict) else result.data
    _store.add_turn(session_gid, "tool_result", "", tool_calls=[{
        "name": tool_name,
        "input": pending["inputs"],
        "result": write_result,
        "tool_use_id": payload.get("tool_use_id", ""),
        "confirmed": True,
    }])
    return {
        "data": {
            "session_gid": session_gid,
            "tool_name": tool_name,
            "result_json": json.dumps(write_result, ensure_ascii=False, separators=(",", ":")),
        }
    }


def register_catalog_tool_confirmation_capability(registry: Any) -> None:
    spec = CapabilitySpec(
        id="agent.catalog_tool.confirm.apply",
        owner="agent",
        description="Execute one previously proposed Catalog-generated Agent tool after explicit user confirmation.",
        use_when="A user confirms the exact pending tool proposal in an owned Agent session.",
        do_not_use_when="Starting or continuing chat, or invoking a tool without a bound confirmation token.",
        risk="write",
        confirmation="user",
        idempotent=False,
        permissions=("agent.interact",),
        input_schema={
            "type": "object",
            "required": ["confirm_token", "tool_name", "session_gid"],
            "properties": {
                "confirm_token": {"type": "string", "minLength": 1, "maxLength": 128},
                "tool_name": {"type": "string", "minLength": 1, "maxLength": 128},
                "session_gid": {"type": "string", "minLength": 1, "maxLength": 128},
                "tool_use_id": {"type": "string", "maxLength": 256},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "required": ["data"],
            "properties": {"data": {
                "type": "object",
                "required": ["session_gid", "tool_name", "result_json"],
                "properties": {
                    "session_gid": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "result_json": {"type": "string", "maxLength": 1_048_576},
                },
                "additionalProperties": False,
            }},
            "additionalProperties": False,
        },
        tags=("agent", "catalog", "tool", "confirmation", "write"),
        plugin_callable=False,
    )
    from .provider import descriptor_for
    descriptor = descriptor_for(spec).model_copy(update={
        "exposure": ExposurePolicy(web=True, api=False, plugin=False, agent=False, mcp=False),
        "consistency_policy": "eventual",
        "evidence_policy": "optional",
        "resource_selectors": (
            ResourceSelector(resource_type="agent-session", payload_path="session_gid", required=True),
        ),
        "business_effect": "One exact Catalog tool proposal is executed for the authenticated owner and its token is consumed once.",
        "business_acceptance_criteria": (
            "The session belongs to the authenticated actor.",
            "The token matches actor, session, tool, payload hash, capability version, and pinned Catalog release.",
            "A successful target invocation consumes the token; a failed target invocation releases it for retry.",
        ),
        "business_invariants": (
            BusinessInvariantContract(
                rule_id="agent.catalog_tool.confirm.bound_once",
                version=1,
                statement="A confirmed Agent tool proposal executes only with its fully bound, single-flight token.",
                applies_when="a user confirms a pending Catalog-generated Agent tool",
                enforcement_ref="plugins/agent/agent_backend/capabilities/catalog_tool_confirmation.py:apply_catalog_tool_confirmation",
                error_code="invalid_input",
                test_refs=("backend/tests/test_agent_interaction_chat_change_boundary.py::test_confirm_route_uses_fixed_governed_confirmation_capability",),
            ),
        ),
        "no_business_invariant_reason": None,
    })
    registry.register(spec, apply_catalog_tool_confirmation, descriptor=descriptor)


__all__ = ["apply_catalog_tool_confirmation", "register_catalog_tool_confirmation_capability"]
