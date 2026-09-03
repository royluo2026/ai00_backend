import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec, CapabilityStreamOutput
from backend.capability_v2.domain_client import DomainCapabilityClient

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
    ResourceSelector,
    TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from backend.capability_v2.reliability import ApprovalService, InMemoryApprovalStore
from backend.capability_v2.authorization import AuthorizationGrants
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.platform_sdk.effective_identity import build_effective_profile
from backend.routers import deps
from backend.scripts.build_capability_catalog import _verified_consumer_refs
from plugins.agent.agent_backend.capabilities.interaction_chat_change import (
    apply_interaction_chat_change,
    register_interaction_chat_change_capability,
)
from plugins.agent.agent_backend.capabilities.catalog_tool_confirmation import (
    apply_catalog_tool_confirmation,
    register_catalog_tool_confirmation_capability,
)
from plugins.agent.agent_backend.capabilities import _authorize_agent_session
from plugins.agent.agent_backend.routers import ai_chat
from plugins.agent.agent_backend.ai_assistant import tool_executor
from plugins.agent.agent_backend.data.confirmation_repository import InMemoryConfirmationRepository
from plugins.agent.agent_backend.capabilities.provider import descriptor_for as agent_descriptor_for
from plugins.agent.agent_backend.ai_assistant.catalog_tools import CatalogToolRegistry, tool_name_for


ROUTER = Path("plugins/agent/agent_backend/routers/ai_chat.py")


def setup_function() -> None:
    tool_executor.configure_confirmation_store(InMemoryConfirmationRepository())


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
    assert {item["consumer_id"] for item in _verified_consumer_refs("agent.catalog_tool.confirm.apply", 1)} == {
        "dist/packages/agent-plugin/web/wfc_window/wfc_window.js",
        "dist/packages/agent-plugin/web/automation_hub/ai_assistant.js",
    }


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
    assert set(v2.spec.output_schema["properties"]["data"]["properties"]) == {
        "stream_id", "media_type", "response_json",
    }


def test_agent_chat_v2_runs_without_a_transaction_participant() -> None:
    registered = CapabilityRegistry()
    register_interaction_chat_change_capability(registered)
    chat = registered.get("agent.interaction.chat.change.apply", 2)
    registry = CapabilityRegistry()
    registry.register(
        chat.spec,
        lambda _payload, _context: {"data": {
            "response_json": "{}",
        }},
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
        payload={"operation": "chat_sync", "body": {"message": "hello"}, "ai00_token": "token"},
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


def test_agent_chat_v2_returns_unconsumed_gateway_stream(monkeypatch) -> None:
    iterated = False

    async def chunks():
        nonlocal iterated
        iterated = True
        yield "data: {}\n\n"

    response = SimpleNamespace(body_iterator=chunks(), media_type="text/event-stream")
    monkeypatch.setattr(ai_chat, "_legacy_chat_stream", lambda *_args: response)

    async def exercise():
        result = await apply_interaction_chat_change(
            {"operation": "chat_stream", "body": {"message": "hi"}},
            SimpleNamespace(user_gid="user-1"),
        )
        assert iterated is False
        assert isinstance(result, CapabilityStreamOutput)
        assert result.media_type == "text/event-stream"
        assert [chunk async for chunk in result.iterator] == ["data: {}\n\n"]

    asyncio.run(exercise())


def test_gateway_owns_stream_lifecycle_until_completion() -> None:
    registered = CapabilityRegistry(); register_interaction_chat_change_capability(registered)
    chat = registered.get("agent.interaction.chat.change.apply", 2)
    release_tail = asyncio.Event()

    async def events():
        yield "data: first\n\n"
        await release_tail.wait()
        yield "data: done\n\n"

    async def broken_events():
        yield "data: first\n\n"
        raise RuntimeError("provider stream failed")

    def stream_output(payload, *_args):
        iterator = broken_events() if payload["body"]["message"] == "explode" else events()
        return CapabilityStreamOutput(
            iterator=iterator, output={"data": {"media_type": "text/event-stream"}},
        )

    registry = CapabilityRegistry()
    registry.register(
        chat.spec,
        stream_output,
        descriptor=chat.descriptor,
    )
    release = build_release([chat.descriptor]); store = InMemoryCatalogStore(); store.publish(release)
    class Policy:
        def authorize(self, *_args): return None
        def approve(self, *_args): return None
        def project(self, _descriptor, _identity, data): return data
    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), Policy(),
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=10)),
    ).bind_release(release.release_id)
    envelope = InvocationEnvelope(
        capability_id=chat.spec.id, major_version=2, catalog_release=release.release_id,
        payload={"operation": "chat_stream", "body": {"message": "hello"}, "ai00_token": "token"},
        identity=ConsumerIdentity(
            actor=ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
            tenant=TenantIdentity(tenant_id="team-1", membership="member"),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.agent"),
        ), request_id="stream-lifecycle-1", trace_id="stream-lifecycle-1",
        idempotency_key="stream-lifecycle-1",
    )

    async def exercise():
        result = await gateway.invoke(envelope)
        assert result.status.value == "accepted"
        assert gateway.recent_metrics() == ()
        stream_id = result.data["data"]["stream_id"]
        iterator, _media = await gateway.claim_stream(stream_id)
        assert await anext(iterator) == "data: first\n\n"
        assert gateway.recent_metrics() == ()
        release_tail.set()
        assert [chunk async for chunk in iterator] == ["data: done\n\n"]
        assert len(gateway.recent_metrics()) == 1
        replay = await gateway.invoke(envelope)
        assert replay.status.value == "completed"
        with pytest.raises(ValueError, match="already claimed"):
            await gateway.claim_stream(stream_id)

        disconnected = envelope.model_copy(update={
            "request_id": "stream-lifecycle-2", "trace_id": "stream-lifecycle-2",
            "idempotency_key": "stream-lifecycle-2",
        })
        disconnected_result = await gateway.invoke(disconnected)
        disconnected_iterator, _media = await gateway.claim_stream(
            disconnected_result.data["data"]["stream_id"]
        )
        assert await anext(disconnected_iterator) == "data: first\n\n"
        await disconnected_iterator.aclose()
        disconnected_replay = await gateway.invoke(disconnected)
        assert disconnected_replay.error.code == "cancelled"

        failed = envelope.model_copy(update={
            "payload": {"operation": "chat_stream", "body": {"message": "explode"}, "ai00_token": "token"},
            "request_id": "stream-lifecycle-3", "trace_id": "stream-lifecycle-3",
            "idempotency_key": "stream-lifecycle-3",
        })
        failed_result = await gateway.invoke(failed)
        failed_iterator, _media = await gateway.claim_stream(failed_result.data["data"]["stream_id"])
        with pytest.raises(RuntimeError, match="provider stream failed"):
            _ = [chunk async for chunk in failed_iterator]
        failed_replay = await gateway.invoke(failed)
        assert failed_replay.error.code == "provider_failed"
        assert len(gateway.recent_metrics()) == 3

    asyncio.run(exercise())


def test_gateway_expires_unclaimed_stream_and_closes_iterator() -> None:
    registered = CapabilityRegistry(); register_interaction_chat_change_capability(registered)
    chat = registered.get("agent.interaction.chat.change.apply", 2)
    closed = 0

    class Events:
        def __aiter__(self): return self
        async def __anext__(self): return "data: never-claimed\n\n"
        async def aclose(self):
            nonlocal closed
            closed += 1

    registry = CapabilityRegistry()
    registry.register(
        chat.spec,
        lambda *_args: CapabilityStreamOutput(
            iterator=Events(), output={"data": {"media_type": "text/event-stream"}},
        ), descriptor=chat.descriptor,
    )
    release = build_release([chat.descriptor]); store = InMemoryCatalogStore(); store.publish(release)
    class Policy:
        def authorize(self, *_args): return None
        def approve(self, *_args): return None
        def project(self, _descriptor, _identity, data): return data
    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), Policy(),
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=10)),
        stream_claim_ttl_seconds=0.01, max_pending_streams=1,
    ).bind_release(release.release_id)
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.agent"),
    )
    envelope = InvocationEnvelope(
        capability_id=chat.spec.id, major_version=2, catalog_release=release.release_id,
        payload={"operation": "chat_stream", "body": {"message": "hello"}, "ai00_token": "token"},
        identity=identity, request_id="stream-expiry-1", trace_id="stream-expiry-1",
        idempotency_key="stream-expiry-1",
    )

    async def exercise():
        result = await gateway.invoke(envelope)
        stream_id = result.data["data"]["stream_id"]
        overflow = await gateway.invoke(envelope.model_copy(update={
            "request_id": "stream-expiry-2", "trace_id": "stream-expiry-2",
            "idempotency_key": "stream-expiry-2",
        }))
        assert overflow.error.code == "stream_capacity_exceeded"
        assert closed == 1
        await asyncio.sleep(0.13)
        assert closed == 2
        assert len(gateway.recent_metrics()) == 2
        with pytest.raises(ValueError, match="expired"):
            await gateway.claim_stream(stream_id)

    asyncio.run(exercise())


def test_agent_chat_v2_preserves_runtime_error_as_sse_without_gateway_buffering(monkeypatch) -> None:
    async def chunks():
        yield 'data: {"type":"error","message":"runtime down"}\n\n'

    response = SimpleNamespace(body_iterator=chunks(), media_type="text/event-stream")
    monkeypatch.setattr(ai_chat, "_legacy_chat_stream", lambda *_args: response)

    async def exercise():
        result = await apply_interaction_chat_change(
            {"operation": "chat_stream", "body": {"message": "hi"}},
            SimpleNamespace(user_gid="user-1"),
        )
        assert isinstance(result, CapabilityStreamOutput)
        return "".join([chunk async for chunk in result.iterator])

    assert asyncio.run(exercise()) == 'data: {"type":"error","message":"runtime down"}\n\n'


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


@pytest.mark.parametrize("method", ["_legacy_chat_stream", "_legacy_chat_sync"])
def test_pi_runtime_checks_session_owner_before_proxy(monkeypatch, method) -> None:
    monkeypatch.setattr(ai_chat._pi_proxy, "enabled", lambda: True)
    monkeypatch.setattr(
        ai_chat,
        "_require_legacy_session_owner",
        lambda *_args: (_ for _ in ()).throw(CapabilityBusinessError("resource_not_found", "missing")),
    )

    with pytest.raises(CapabilityBusinessError, match="missing"):
        getattr(ai_chat, method)({"session_gid": "foreign"}, {"gid": "user-1"}, "token")


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
    async def exercise() -> tuple[object, str]:
        async def events():
            yield 'data: {"type":"done"}\n\n'

        stream_id = "capability-stream-" + "a" * 32

        class Gateway:
            catalog_release = "release-1"
            claimed = False

            async def invoke(self, _envelope):
                return SimpleNamespace(
                    ok=True,
                    data={"data": {"stream_id": stream_id, "media_type": "text/event-stream"}},
                    error=None,
                )
            async def claim_stream(self, claimed_id):
                assert claimed_id == stream_id and not self.claimed
                self.claimed = True
                return events(), "text/event-stream"

        response = await ai_chat._invoke_interaction_chat(
            SimpleNamespace(headers={}),
            {"gid": "admin-1", "team_id": "team-1", "org_role": "super_admin"},
            ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
            Gateway(),
            {"operation": "chat_stream", "body": {"message": "hello"}, "ai00_token": "token"},
        )
        body = "".join([
            chunk.decode() if isinstance(chunk, bytes) else chunk
            async for chunk in response.body_iterator
        ])
        return response, body

    response, body = asyncio.run(exercise())
    assert response.media_type == "text/event-stream"
    assert body == 'data: {"type":"done"}\n\n'


def test_asgi_stream_emits_first_body_before_agent_finishes() -> None:
    async def exercise() -> None:
        release_tail = asyncio.Event()
        first_body = asyncio.Event()
        sent = []

        async def events():
            yield 'data: {"type":"token","content":"a"}\n\n'
            await release_tail.wait()
            yield 'data: {"type":"done"}\n\n'

        stream_id = "capability-stream-" + "b" * 32
        class Gateway:
            async def claim_stream(self, claimed_id):
                assert claimed_id == stream_id
                return events(), "text/event-stream"
        response = await ai_chat._project_interaction_response(
            {"operation": "chat_stream"},
            {"stream_id": stream_id, "media_type": "text/event-stream"},
            gateway=Gateway(),
        )
        received_request = False

        async def receive():
            nonlocal received_request
            if not received_request:
                received_request = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()

        async def send(message):
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                first_body.set()

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/api/ai/chat/stream",
            "raw_path": b"/api/ai/chat/stream", "query_string": b"",
            "headers": [], "client": ("test", 1), "server": ("test", 80),
        }
        task = asyncio.create_task(response(scope, receive, send))
        await asyncio.wait_for(first_body.wait(), timeout=0.5)
        assert task.done() is False
        assert sent[0]["type"] == "http.response.start"
        assert sent[1]["body"].startswith(b"data: ")
        release_tail.set()
        await asyncio.wait_for(task, timeout=0.5)

    asyncio.run(exercise())


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


def test_confirm_route_uses_fixed_governed_confirmation_capability(monkeypatch) -> None:
    calls = []

    class Gateway:
        catalog_release = "release-1"

        async def invoke(self, envelope):
            calls.append(envelope)
            data = {"data": {"session_gid": "session-1"}} if len(calls) == 1 else {"data": {"response_json": '{"answer":"continued"}'}}
            return SimpleNamespace(ok=True, data=data, error=None)

    tool_name = "cap__project__task__change__apply__v1"
    response = asyncio.run(ai_chat._invoke_confirmed_catalog_tool(
        SimpleNamespace(headers={}),
        {"gid": "admin-1", "team_id": "team-1", "org_role": "super_admin"},
        ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        Gateway(),
        {"confirm_token": "token-1", "tool_name": tool_name, "session_gid": "session-1", "stream": False},
    ))

    assert [call.capability_id for call in calls] == [
        "agent.catalog_tool.confirm.apply", "agent.interaction.chat.change.apply",
    ]
    assert calls[0].identity.consumer.consumer_id == "ai00.web.agent"
    assert calls[0].payload == {
        "confirm_token": "token-1", "tool_name": tool_name,
        "session_gid": "session-1", "tool_use_id": "",
    }
    assert response == {"answer": "continued"}


def test_catalog_tool_confirmation_is_user_confirmed_and_not_model_exposed() -> None:
    registry = CapabilityRegistry()
    register_catalog_tool_confirmation_capability(registry)
    registered = registry.get("agent.catalog_tool.confirm.apply", 1)

    assert registered.spec.confirmation == "user"
    assert registered.descriptor.exposure.web is True
    assert registered.descriptor.exposure.api is False
    assert registered.descriptor.exposure.plugin is False
    assert registered.descriptor.exposure.agent is False
    assert registered.descriptor.exposure.mcp is False
    assert substantive_business_definition_errors(registered.descriptor) == ()
    assert [(item.resource_type, item.payload_path) for item in registered.descriptor.resource_selectors] == [
        ("agent-session", "session_gid"),
    ]


def test_member_confirmation_passes_real_gateway_resource_authorization(monkeypatch) -> None:
    registered = CapabilityRegistry()
    register_catalog_tool_confirmation_capability(registered)
    confirmation = registered.get("agent.catalog_tool.confirm.apply", 1)
    registry = CapabilityRegistry()
    registry.register(
        confirmation.spec,
        lambda payload, _context: {"data": {
            "session_gid": payload["session_gid"], "tool_name": payload["tool_name"],
            "result_json": "{}",
        }},
        descriptor=confirmation.descriptor,
    )
    release = build_release([confirmation.descriptor])
    store = InMemoryCatalogStore(); store.publish(release)
    monkeypatch.setattr(
        "plugins.agent.agent_backend.capabilities.SessionRepository.require_owned_session",
        lambda _self, session_gid, user_gid: None if (session_gid, user_gid) == ("owned", "member-1")
        else (_ for _ in ()).throw(CapabilityBusinessError("resource_not_found", "missing")),
    )
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda _gid: {"gid": "member-1", "is_active": True},
        grants_resolver=lambda _identity, _user: AuthorizationGrants(
            permissions=("agent.interact",), capability_scopes=("*",),
            resource_scopes=(), data_scopes=("confidential",), policy_version="test-1",
        ),
        approval_service=ApprovalService(InMemoryApprovalStore()),
        resource_authorizer=lambda ref, identity, _user: (
            ref.startswith("agent-session:")
            and _authorize_agent_session(ref.split(":", 1)[1], identity)
        ),
    )
    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), policy,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=20)),
    ).bind_release(release.release_id)
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="member-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="member", active_roles=("member",)),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.agent"),
    )
    def envelope(session_gid, request_id):
        return InvocationEnvelope(
            capability_id=confirmation.spec.id, major_version=1,
            catalog_release=release.release_id,
            payload={"confirm_token": "token", "tool_name": "cap__x__v1", "session_gid": session_gid, "tool_use_id": "call"},
            identity=identity, request_id=request_id, trace_id=request_id,
            idempotency_key=request_id,
        )

    owned = envelope("owned", "owned-request")
    challenge = asyncio.run(gateway.invoke(owned))
    assert challenge.error.code == "confirmation_required"
    approval = asyncio.run(gateway.request_approval(owned))
    accepted = asyncio.run(gateway.invoke(owned.model_copy(update={"approval_reference": approval.token})))
    assert accepted.ok is True
    foreign = asyncio.run(gateway.invoke(envelope("foreign", "foreign-request")))
    assert foreign.error.code == "resource_scope_denied"


def test_confirmed_catalog_tool_reaches_target_as_session_bound_agent_identity(monkeypatch) -> None:
    registry = CapabilityRegistry()
    register_catalog_tool_confirmation_capability(registry)
    target_spec = CapabilitySpec(
        id="agent.test.change.apply", owner="agent",
        description="Test one delegated Agent target envelope.",
        use_when="Testing delegated target identity.", do_not_use_when="Outside tests.",
        risk="write", confirmation="user", idempotent=False,
        permissions=("agent.interact",),
        input_schema={"type": "object", "required": ["task_gid", "value"], "properties": {"task_gid": {"type": "string"}, "value": {"type": "integer"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "required": ["value"], "properties": {"value": {"type": "integer"}}, "additionalProperties": False}}, "additionalProperties": False},
        plugin_callable=True,
    )
    captured = []
    registry.register(
        target_spec,
        lambda payload, context: captured.append(context.effective_identity) or {"data": {"value": payload["value"]}},
        descriptor=agent_descriptor_for(target_spec).model_copy(update={
            "consistency_policy": "eventual",
            "evidence_policy": "optional",
            "resource_selectors": (
                ResourceSelector(
                    resource_type="project-task", payload_path="task_gid", required=True,
                ),
            ),
        }),
    )
    release = build_release([item.descriptor for item in registry.snapshot()])
    store = InMemoryCatalogStore(); store.publish(release)
    monkeypatch.setattr(ai_chat._store, "require_owned_session", lambda *_args: None)
    monkeypatch.setattr(ai_chat._store, "add_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "plugins.agent.agent_backend.capabilities.SessionRepository.require_owned_session",
        lambda *_args: None,
    )
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda _gid: {"gid": "member-1", "is_active": True},
        grants_resolver=lambda _identity, _user: AuthorizationGrants(
            permissions=("agent.interact",), capability_scopes=("*",),
            resource_scopes=(), data_scopes=("confidential",), policy_version="test-1",
        ),
        approval_service=ApprovalService(InMemoryApprovalStore()),
        resource_authorizer=lambda ref, identity, _user: (
            ref == "project-task:task-7"
            or (
                ref.startswith("agent-session:")
                and _authorize_agent_session(ref.split(":", 1)[1], identity)
            )
        ),
    )
    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), policy,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=30)),
    ).bind_release(release.release_id)
    web_identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="member-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="member", active_roles=("member",)),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.agent"),
    )
    tool_name = tool_name_for(target_spec.id, 1)
    tool = CatalogToolRegistry(release).resolve(tool_name)
    tool_inputs = {"task_gid": "task-7", "value": 7}
    delegated = DomainCapabilityClient(gateway).issue_agent_run_identity(
        web_identity, agent_run_id="run-real-1", session_gid="session-1",
        capability_scopes=(target_spec.id,),
        resource_scopes=tool.resource_scopes(tool_inputs),
    )
    token = tool_executor.issue_confirm_token(
        tool_name, tool_inputs, "session-1", "member-1",
        catalog_release=release.release_id, capability_id=target_spec.id,
        major_version=1, idempotency_key="stable-target-1", agent_identity=delegated,
    )
    parent = InvocationEnvelope(
        capability_id="agent.catalog_tool.confirm.apply", major_version=1,
        catalog_release=release.release_id,
        payload={"confirm_token": token, "tool_name": tool_name, "session_gid": "session-1", "tool_use_id": "call-1"},
        identity=web_identity, request_id="confirm-real-1", trace_id="trace-real-1",
        idempotency_key="confirm-real-1",
    )

    challenge = asyncio.run(gateway.invoke(parent))
    assert challenge.error.code == "confirmation_required"
    approval = asyncio.run(gateway.request_approval(parent))
    result = asyncio.run(gateway.invoke(parent.model_copy(update={"approval_reference": approval.token})))

    assert result.ok is True, result.error
    assert len(captured) == 1
    target_identity = captured[0]
    assert target_identity.consumer.type is ConsumerType.AGENT
    assert target_identity.consumer.agent_run_id == "run-real-1"
    assert target_identity.delegation.catalog_release == release.release_id
    assert target_identity.delegation.resource_scopes == (
        "agent-session:session-1", "project-task:task-7",
    )
    assert target_identity.delegation.capability_scopes == (target_spec.id,)


def test_catalog_tool_confirmation_resolves_pinned_record_and_consumes_after_success(monkeypatch) -> None:
    from backend.capability_v2.catalog import load_catalog_release
    from plugins.agent.agent_backend.ai_assistant.catalog_tools import CatalogToolRegistry

    release = load_catalog_release(
        Path("docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    tool = next(item for item in CatalogToolRegistry(release).tools() if item.confirmation_policy != "none")
    calls = []
    stored = []

    class Client:
        catalog_release = release.release_id

        def catalog(self):
            return release

        async def _invoke_from_confirmed_parent(self, invocation, identity, correlation):
            calls.append((invocation, identity, correlation))
            return SimpleNamespace(ok=True, data={"data": {"gid": "created-1"}}, error=None)

    monkeypatch.setattr(ai_chat._store, "require_owned_session", lambda *_args: None)
    monkeypatch.setattr(ai_chat._store, "add_turn", lambda *args, **kwargs: stored.append((args, kwargs)))
    token = tool_executor.issue_confirm_token(
        tool.name, {}, "session-1", "admin-1",
        catalog_release=release.release_id,
        capability_id=tool.capability_id,
        major_version=tool.major_version,
        agent_identity=ConsumerIdentity(
            actor=ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
            tenant=TenantIdentity(tenant_id="team-1", membership="member"),
            consumer=ConsumerDescriptor(type=ConsumerType.AGENT, consumer_id="agent.xiaorou", agent_run_id="run-1"),
        ),
    )
    context = SimpleNamespace(
        user_gid="admin-1", request_id="request-1", idempotency_key="idem-1",
        domain_client=Client(), effective_identity=SimpleNamespace(),
    )

    response = asyncio.run(apply_catalog_tool_confirmation({
        "confirm_token": token, "tool_name": tool.name,
        "session_gid": "session-1", "tool_use_id": "call-1",
    }, context))

    assert calls[0][0].capability_id == tool.capability_id
    assert calls[0][0].major_version == tool.major_version
    assert json.loads(response["data"]["result_json"]) == {"gid": "created-1"}
    assert stored
    assert tool_executor._token_hash(token) not in tool_executor._CONFIRM_STORE.records


def test_catalog_tool_confirmation_releases_token_when_cancelled(monkeypatch) -> None:
    from backend.capability_v2.catalog import load_catalog_release
    from plugins.agent.agent_backend.ai_assistant.catalog_tools import CatalogToolRegistry

    release = load_catalog_release(
        Path("docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    tool = next(item for item in CatalogToolRegistry(release).tools() if item.confirmation_policy != "none")

    class Client:
        catalog_release = release.release_id
        def catalog(self): return release
        async def _invoke_from_confirmed_parent(self, *_args):
            raise asyncio.CancelledError()

    monkeypatch.setattr(ai_chat._store, "require_owned_session", lambda *_args: None)
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.AGENT, consumer_id="agent.xiaorou", agent_run_id="run-1"),
    )
    token = tool_executor.issue_confirm_token(
        tool.name, {}, "session-1", "admin-1",
        catalog_release=release.release_id, capability_id=tool.capability_id,
        major_version=tool.major_version, agent_identity=identity,
    )
    context = SimpleNamespace(
        user_gid="admin-1", request_id="request-1", idempotency_key="idem-1",
        domain_client=Client(), effective_identity=SimpleNamespace(),
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(apply_catalog_tool_confirmation({
            "confirm_token": token, "tool_name": tool.name,
            "session_gid": "session-1", "tool_use_id": "call-1",
        }, context))

    valid, _ = tool_executor.begin_confirm_token(
        token, tool.name, "session-1", "admin-1",
        catalog_release=release.release_id, capability_id=tool.capability_id,
        major_version=tool.major_version,
    )
    assert valid is True


def test_catalog_tool_confirmation_reuses_stable_idempotency_after_unknown_outcome(monkeypatch) -> None:
    from backend.capability_v2.catalog import load_catalog_release
    from plugins.agent.agent_backend.ai_assistant.catalog_tools import CatalogToolRegistry

    release = load_catalog_release(
        Path("docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    tool = next(item for item in CatalogToolRegistry(release).tools() if item.confirmation_policy != "none")
    calls = []

    class Client:
        catalog_release = release.release_id
        def catalog(self): return release
        async def _invoke_from_confirmed_parent(self, invocation, *_args):
            calls.append(invocation)
            if len(calls) == 1:
                return SimpleNamespace(
                    ok=False, data={},
                    error=SimpleNamespace(
                        code="outcome_unknown", message="reconcile and retry",
                        retryable=True, details={},
                    ),
                )
            return SimpleNamespace(ok=True, data={"data": {"gid": "created-1"}}, error=None)

    monkeypatch.setattr(ai_chat._store, "require_owned_session", lambda *_args: None)
    monkeypatch.setattr(ai_chat._store, "add_turn", lambda *_args, **_kwargs: None)
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="admin-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.AGENT, consumer_id="agent.xiaorou", agent_run_id="run-1"),
    )
    token = tool_executor.issue_confirm_token(
        tool.name, {}, "session-1", "admin-1",
        catalog_release=release.release_id, capability_id=tool.capability_id,
        major_version=tool.major_version, agent_identity=identity,
        idempotency_key="stable-confirmed-write-1",
    )
    context = SimpleNamespace(
        user_gid="admin-1", request_id="request-1", idempotency_key="outer-idem",
        domain_client=Client(), effective_identity=SimpleNamespace(),
    )
    payload = {
        "confirm_token": token, "tool_name": tool.name,
        "session_gid": "session-1", "tool_use_id": "call-1",
    }

    with pytest.raises(CapabilityBusinessError) as raised:
        asyncio.run(apply_catalog_tool_confirmation(payload, context))
    assert raised.value.code == "outcome_unknown"
    response = asyncio.run(apply_catalog_tool_confirmation(payload, context))

    assert json.loads(response["data"]["result_json"]) == {"gid": "created-1"}
    assert [call.idempotency_key for call in calls] == [
        "stable-confirmed-write-1", "stable-confirmed-write-1",
    ]


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
