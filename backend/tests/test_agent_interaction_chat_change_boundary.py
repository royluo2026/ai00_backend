import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from backend.capability_v2.provider_contracts import CapabilityBusinessError

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.business_definition import substantive_business_definition_errors
from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from backend.platform_sdk.effective_identity import build_effective_profile
from backend.routers import deps
from backend.scripts.build_capability_catalog import _verified_consumer_refs
from plugins.agent.agent_backend.capabilities.interaction_chat_change import (
    apply_interaction_chat_change,
    register_interaction_chat_change_capability,
)
from plugins.agent.agent_backend.routers import ai_chat
from plugins.agent.agent_backend.ai_assistant import tool_executor


ROUTER = Path("plugins/agent/agent_backend/routers/ai_chat.py")


def test_agent_chat_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="agent.interaction.chat.change.apply"') == 1
    for name in ("chat_stream", "chat_sync", "confirm_tool", "confirm_tool_sync"):
        assert f"def _legacy_{name}" in source


def test_agent_chat_v2_has_verified_web_consumers() -> None:
    refs = _verified_consumer_refs("agent.interaction.chat.change.apply", 2)
    assert {item["consumer_id"] for item in refs} == {
        "dist/web/workbench/workbench.js",
        "dist/packages/agent-plugin/web/wfc_window/wfc_window.js",
        "dist/packages/agent-plugin/web/automation_hub/ai_assistant.js",
    }
    assert _verified_consumer_refs("agent.interaction.chat.change.apply", 1) == ()


def test_agent_chat_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        asyncio.run(apply_interaction_chat_change({"operation": "delete", "body": {}}, object()))


def test_agent_chat_registers_frozen_v1_and_corrected_v2() -> None:
    registry = CapabilityRegistry()
    register_interaction_chat_change_capability(registry)
    v1 = registry.get("agent.interaction.chat.change.apply", 1)
    v2 = registry.get("agent.interaction.chat.change.apply", 2)

    assert v1.spec.confirmation == "user"
    assert v1.descriptor.consistency_policy == "strong"
    assert v1.descriptor.evidence_policy == "required"
    assert "context_json" not in v1.spec.input_schema["properties"]["body"]["properties"]
    assert set(v1.spec.output_schema["properties"]["data"]["properties"]) == {
        "events", "media_type", "answer", "session_id",
    }
    assert v2.spec.version == 2
    assert v2.spec.input_schema["properties"]["operation"]["enum"] == ["chat_stream", "chat_sync"]
    assert v2.spec.confirmation == "none"
    assert v2.descriptor.consistency_policy == "eventual"
    assert v2.descriptor.evidence_policy == "optional"
    assert v2.descriptor.idempotency_policy == "required"
    assert {
        (selector.resource_type, selector.payload_path, selector.required)
        for selector in v2.descriptor.resource_selectors
    } == {
        ("agent-session", "body.session_id", False),
        ("agent-session", "body.session_gid", False),
    }
    assert substantive_business_definition_errors(v2.descriptor) == ()
    assert {rule.rule_id for rule in v2.descriptor.business_invariants} == {
        "agent.interaction.chat.actor_bound",
        "agent.interaction.chat.session_owned",
    }
    assert v2.spec.input_schema["properties"]["body"]["additionalProperties"] is False
    assert v2.spec.output_schema["properties"]["data"]["additionalProperties"] is False


def test_agent_chat_v2_runs_without_a_transaction_participant() -> None:
    registered = CapabilityRegistry()
    register_interaction_chat_change_capability(registered)
    chat = registered.get("agent.interaction.chat.change.apply", 2)
    registry = CapabilityRegistry()
    registry.register(
        chat.spec,
        lambda _payload, _context: {"data": {"events": [], "media_type": "text/event-stream"}},
        descriptor=chat.descriptor,
    )
    release = build_release([chat.descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)

    class Policy:
        def authorize(self, *_args):
            return None

        def approve(self, *_args):
            return None

        def project(self, _descriptor, _identity, data):
            return data

    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry),
        Policy(),
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=10)),
    ).bind_release(release.release_id)
    envelope = InvocationEnvelope(
        capability_id=chat.spec.id,
        major_version=2,
        catalog_release=release.release_id,
        payload={"operation": "chat_stream", "body": {"message": "hello"}, "ai00_token": "token"},
        identity=ConsumerIdentity(
            actor=ActorIdentity(
                user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)
            ),
            tenant=TenantIdentity(
                tenant_id="team-1", membership="member", active_roles=("super_admin",)
            ),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.agent"),
        ),
        request_id="request-agent-chat",
        trace_id="trace-agent-chat",
        idempotency_key="request-agent-chat",
    )

    result = asyncio.run(gateway.invoke(envelope))

    assert result.ok is True, result.error


def test_agent_chat_v2_rejects_non_object_context_json(monkeypatch) -> None:
    monkeypatch.setattr(ai_chat, "_legacy_chat_sync", lambda *_args: {"answer": "ok"})

    with pytest.raises(ValueError, match="context_json must encode an object"):
        asyncio.run(apply_interaction_chat_change(
            {"operation": "chat_sync", "body": {"message": "hi", "context_json": "[]"}},
            SimpleNamespace(user_gid="user-1"),
        ))


def test_agent_chat_v2_rejects_more_than_500_stream_events(monkeypatch) -> None:
    async def chunks():
        for _ in range(501):
            yield "data: {}\n\n"

    response = SimpleNamespace(body_iterator=chunks(), media_type="text/event-stream")
    monkeypatch.setattr(ai_chat, "_legacy_chat_stream", lambda *_args: response)

    with pytest.raises(ValueError, match="stream response exceeds 500 events"):
        asyncio.run(apply_interaction_chat_change(
            {"operation": "chat_stream", "body": {"message": "hi"}},
            SimpleNamespace(user_gid="user-1"),
        ))


def test_agent_chat_v2_rejects_oversized_sync_response(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_chat,
        "_legacy_chat_sync",
        lambda *_args: {"answer": "x" * 1_048_577},
    )

    with pytest.raises(ValueError, match="synchronous response exceeds 1048576 characters"):
        asyncio.run(apply_interaction_chat_change(
            {"operation": "chat_sync", "body": {"message": "hi"}},
            SimpleNamespace(user_gid="user-1"),
        ))


def test_agent_chat_v2_projects_legacy_failure_as_business_error(monkeypatch) -> None:
    monkeypatch.setattr(ai_chat, "_legacy_chat_sync", lambda *_args: {"error": "runtime down"})

    with pytest.raises(CapabilityBusinessError) as exc_info:
        asyncio.run(apply_interaction_chat_change(
            {"operation": "chat_sync", "body": {"message": "hi"}},
            SimpleNamespace(user_gid="user-1"),
        ))

    assert exc_info.value.code == "provider_unavailable"


def test_agent_chat_rejects_a_foreign_session(monkeypatch) -> None:
    checked = []
    monkeypatch.setattr(ai_chat._store, "require_owned_session", lambda session_gid, user_gid: checked.append((session_gid, user_gid)) if session_gid == "owned-session" else (_ for _ in ()).throw(CapabilityBusinessError("resource_not_found", "Agent session was not found")))

    ai_chat._require_legacy_session_owner("owned-session", "admin-1")
    with pytest.raises(CapabilityBusinessError) as exc_info:
        ai_chat._require_legacy_session_owner("foreign-session", "admin-1")

    assert exc_info.value.code == "resource_not_found"
    assert checked == [("owned-session", "admin-1")]


def test_web_chat_pins_v2_and_normalizes_trusted_payload() -> None:
    registered = CapabilityRegistry()
    register_interaction_chat_change_capability(registered)
    descriptor = registered.get("agent.interaction.chat.change.apply", 2).descriptor
    captured = []

    class Gateway:
        catalog_release = "release-1"

        async def invoke(self, envelope):
            captured.append(envelope)
            return SimpleNamespace(
                ok=True,
                data={"data": {"response_json": '{"answer":"ok"}'}},
                error=None,
            )

    response = asyncio.run(ai_chat._invoke_interaction_chat(
        SimpleNamespace(headers={}),
        {"gid": "admin-1", "team_id": "team-1", "org_role": "super_admin"},
        ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        Gateway(),
        {
            "operation": "chat_sync",
            "body": {
                "message": "hello",
                "user_gid": "untrusted-user",
                "context": {"current_page": "workbench"},
            },
            "ai00_token": "token",
        },
    ))

    envelope = captured[0]
    validate_payload(dict(descriptor.input_schema), dict(envelope.payload))
    assert envelope.major_version == 2
    assert envelope.identity.actor.user_id == "admin-1"
    assert envelope.identity.consumer.consumer_id == "ai00.web.agent"
    assert "user_gid" not in envelope.payload["body"]
    assert json.loads(envelope.payload["body"]["context_json"]) == {
        "current_page": "workbench"
    }
    assert response == {"answer": "ok"}


def test_web_stream_chat_restores_the_sse_response() -> None:
    class Gateway:
        catalog_release = "release-1"

        async def invoke(self, _envelope):
            return SimpleNamespace(
                ok=True,
                data={"data": {"events": ['data: {"type":"done"}\n\n'], "media_type": "text/event-stream"}},
                error=None,
            )

    response = asyncio.run(ai_chat._invoke_interaction_chat(
        SimpleNamespace(headers={}),
        {"gid": "admin-1", "team_id": "team-1", "org_role": "super_admin"},
        ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        Gateway(),
        {"operation": "chat_stream", "body": {"message": "hello"}, "ai00_token": "token"},
    ))

    async def collect() -> str:
        return "".join([
            chunk.decode() if isinstance(chunk, bytes) else chunk
            async for chunk in response.body_iterator
        ])

    assert response.media_type == "text/event-stream"
    assert asyncio.run(collect()) == 'data: {"type":"done"}\n\n'


def test_web_sync_chat_restores_the_bounded_response() -> None:
    class Gateway:
        catalog_release = "release-1"

        async def invoke(self, _envelope):
            return SimpleNamespace(
                ok=True,
                data={"data": {"response_json": '{"answer":"ok","tool_calls":[]}'}},
                error=None,
            )

    response = asyncio.run(ai_chat._invoke_interaction_chat(
        SimpleNamespace(headers={}),
        {"gid": "admin-1", "team_id": "team-1", "org_role": "super_admin"},
        ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        Gateway(),
        {"operation": "chat_sync", "body": {"message": "hello"}, "ai00_token": "token"},
    ))

    assert response == {"answer": "ok", "tool_calls": []}


def test_confirm_route_uses_catalog_reverse_mapping_then_governed_chat(monkeypatch) -> None:
    calls = []
    stored = []
    monkeypatch.setattr(ai_chat, "_require_legacy_session_owner", lambda *_args: None)
    monkeypatch.setattr(ai_chat._store, "add_turn", lambda *args, **kwargs: stored.append((args, kwargs)))
    monkeypatch.setattr(
        ai_chat,
        "CatalogToolRegistry",
        lambda _release: SimpleNamespace(resolve=lambda name: SimpleNamespace(
            name=name, capability_id="project.task.change.apply", major_version=1,
        )),
    )

    class Gateway:
        catalog_release = "release-1"

        def catalog(self, _release_id):
            return object()

        async def invoke(self, envelope):
            calls.append(envelope)
            data = {"data": {"gid": "task-1"}} if len(calls) == 1 else {"data": {"response_json": '{"answer":"continued"}'}}
            return SimpleNamespace(ok=True, data=data, error=None)

    tool_name = "cap__project__task__change__apply__v1"
    token = tool_executor.issue_confirm_token(tool_name, {"name": "x"}, "session-1", "admin-1")
    response = asyncio.run(ai_chat._invoke_confirmed_catalog_tool(
        SimpleNamespace(headers={}),
        {"gid": "admin-1", "team_id": "team-1", "org_role": "super_admin"},
        ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        Gateway(),
        {"confirm_token": token, "tool_name": tool_name, "session_gid": "session-1", "stream": False},
    ))

    assert [call.capability_id for call in calls] == [
        "project.task.change.apply", "agent.interaction.chat.change.apply",
    ]
    assert calls[0].identity.consumer.consumer_id == "ai00.web.agent"
    assert response == {"answer": "continued"}
    assert stored


def test_web_chat_rejects_non_object_context_before_gateway() -> None:
    with pytest.raises(HTTPException) as raised:
        ai_chat._normalize_interaction_payload({
            "operation": "chat_sync",
            "body": {"message": "hello", "context": []},
        })

    assert raised.value.status_code == 400
    assert raised.value.detail == "context must be an object"


@pytest.mark.parametrize(
    ("system_role", "org_role"),
    (("member", "member"), ("super_admin", "super_admin")),
)
def test_internal_user_can_authorize_agent_chat(monkeypatch, system_role, org_role) -> None:
    user = {
        "gid": f"{system_role}-1",
        "system_role": system_role,
        "org_role": org_role,
        "is_active": True,
    }
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])

    assert "agent.interact" in deps.build_profile(user)["permissions"]
    assert "agent.interact" in build_effective_profile(user, [])["permissions"]


def test_external_user_cannot_authorize_agent_chat(monkeypatch) -> None:
    user = {
        "gid": "external-1",
        "system_role": "member",
        "org_role": "external",
        "is_active": True,
    }
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])

    assert "agent.interact" not in deps.build_profile(user)["permissions"]
    assert "agent.interact" not in build_effective_profile(user, [])["permissions"]


def test_internal_user_can_read_agent_settings(monkeypatch) -> None:
    user = {"gid": "admin-1", "system_role": "super_admin", "org_role": "super_admin", "is_active": True}
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])

    assert "agent.read" in deps.build_profile(user)["permissions"]
    assert "agent.read" in build_effective_profile(user, [])["permissions"]


def test_external_user_cannot_read_agent_settings(monkeypatch) -> None:
    user = {"gid": "external-1", "system_role": "member", "org_role": "external", "is_active": True}
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])

    assert "agent.read" not in deps.build_profile(user)["permissions"]
    assert "agent.read" not in build_effective_profile(user, [])["permissions"]
