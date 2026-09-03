import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
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
from plugins.agent.agent_backend.capabilities.interaction_chat_change import (
    apply_interaction_chat_change,
    register_interaction_chat_change_capability,
)
from plugins.agent.agent_backend.routers import ai_chat


ROUTER = Path("plugins/agent/agent_backend/routers/ai_chat.py")


def test_agent_chat_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="agent.interaction.chat.change.apply"') == 1
    for name in ("chat_stream", "chat_sync", "confirm_tool", "confirm_tool_sync"):
        assert f"def _legacy_{name}" in source


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
    assert v2.spec.confirmation == "none"
    assert v2.descriptor.consistency_policy == "eventual"
    assert v2.descriptor.evidence_policy == "optional"
    assert v2.descriptor.idempotency_policy == "required"
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
