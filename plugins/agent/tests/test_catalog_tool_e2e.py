import asyncio
import builtins
import json
import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.capability_v2.catalog import load_catalog_release
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, CorrelationRef, TenantIdentity
from plugins.agent.agent_backend.ai_assistant.catalog_tools import CatalogToolRegistry, tool_name_for
from plugins.agent.agent_backend.ai_assistant import tool_executor, tool_registry
from plugins.agent.agent_backend.routers import ai_chat
from plugins.agent.agent_backend.data.confirmation_repository import InMemoryConfirmationRepository


def setup_function() -> None:
    tool_executor.configure_confirmation_store(InMemoryConfirmationRepository())


def test_chat_stream_missing_key_points_to_runtime_deployment_secret(monkeypatch):
    monkeypatch.setattr(
        ai_chat,
        "_get_ai_config",
        lambda *_args: {"model": "", "api_key": "", "api_base": ""},
    )

    chunks = list(ai_chat._chat_stream_gen(
        "hello", None, "user-1", "feishu", "", None,
    ))

    assert len(chunks) == 1
    event = json.loads(chunks[0][6:])
    assert event == {
        "type": "error",
        "message": "未配置 AI API Key；请在 Agent Runtime 部署 Secret 中配置",
    }


def test_tool_name_is_deterministic_and_bounded():
    assert tool_name_for("craft.bop.version.get", 1) == "cap__craft__bop__version__get__v1"
    with pytest.raises(ValueError, match="128"):
        tool_name_for("x." + "y" * 130, 1)


def test_agent_tools_equal_pinned_catalog_exposure():
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = CatalogToolRegistry(release)
    expected = {tool_name_for(item.id, item.major_version) for item in release.descriptors if item.exposure.agent}
    assert set(registry.names()) == expected
    assert all(tool.capability_id for tool in registry.tools())


def test_catalog_tool_executes_stored_reverse_mapping_through_domain_client():
    calls = []
    class Client:
        async def invoke(self, invocation, identity, correlation, deadline=None):
            calls.append((invocation, identity, correlation)); return {"status": "succeeded"}
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = CatalogToolRegistry(release, client=Client())
    tool = next(item for item in registry.tools() if item.capability_id == "system.search")
    identity = ConsumerIdentity(
        actor=ActorIdentity(service_id="agent-runtime", authentication_method="service-token", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="tenant-1", membership="service"),
        consumer=ConsumerDescriptor(type=ConsumerType.AGENT, consumer_id="domain.agent", agent_run_id="run-1"),
    )
    asyncio.run(registry.execute(tool.name, {}, identity=identity, correlation=CorrelationRef(request_id="r1", trace_id="t1")))
    invocation, _, _ = calls[-1]
    assert invocation.capability_id == "system.search"
    assert invocation.major_version == 1


def test_runtime_registry_and_executor_use_catalog_records_without_name_inference():
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = tool_registry.build_catalog_tool_registry(release)
    definitions = tool_registry.catalog_tools_openai(registry)
    assert {item["function"]["name"] for item in definitions} == set(registry.names())
    assert hasattr(tool_executor, "execute_catalog_tool")


def test_catalog_registry_resolves_only_stored_reverse_mappings():
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = CatalogToolRegistry(release)
    known = registry.names()[0]

    assert registry.resolve(known).name == known
    with pytest.raises(ValueError, match="unknown Catalog-generated Agent tool"):
        registry.resolve("create_task")


def test_real_chat_loop_issues_bound_token_from_pinned_catalog(monkeypatch):
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = CatalogToolRegistry(release)
    tool = next(item for item in registry.tools() if item.confirmation_policy != "none")
    captured_tools = []
    original_import = builtins.__import__
    monkeypatch.setattr(
        builtins,
        "__import__",
        lambda name, *args, **kwargs: (
            (_ for _ in ()).throw(ImportError("litellm is intentionally absent"))
            if name == "litellm" else original_import(name, *args, **kwargs)
        ),
    )

    monkeypatch.setattr(ai_chat, "_get_ai_config", lambda *_args: {"model": "kivy-test", "api_key": "key", "api_base": ""})
    monkeypatch.setattr(ai_chat._sp, "build", lambda **_kwargs: "system")
    monkeypatch.setattr(ai_chat._store, "add_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_chat._store, "get_turns", lambda *_args: [])
    monkeypatch.setattr(ai_chat, "consume_abort", lambda *_args: False)
    from plugins.agent.agent_backend.ai_assistant import task_classifier
    from plugins.agent.agent_backend.ai_assistant import orchestrator
    monkeypatch.setattr(task_classifier, "classify_task", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orchestrator, "should_orchestrate", lambda *_args: False)

    def completion(**kwargs):
        captured_tools.extend(kwargs["tools"])
        return {
            "usage": {"total_tokens": 1},
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-1", "function": {"name": tool.name, "arguments": "{}"},
            }]}}],
        }

    monkeypatch.setattr(ai_chat, "_chj_completion", completion)
    runtime = {
        "registry": registry,
        "identity_factory": lambda _session_gid, _tool, _inputs: ConsumerIdentity(
            actor=ActorIdentity(user_id="user-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
            tenant=TenantIdentity(tenant_id="tenant-1", membership="member"),
            consumer=ConsumerDescriptor(type=ConsumerType.AGENT, consumer_id="agent.xiaorou", agent_run_id="run-1"),
        ),
        "correlation": SimpleNamespace(request_id="request-1"),
        "catalog_release": release.release_id,
    }

    chunks = list(ai_chat._chat_stream_gen(
        "do it", "session-1", "user-1", "feishu", "", None,
        catalog_runtime=runtime,
    ))
    assert any('confirm_required' in chunk for chunk in chunks), chunks
    event = next(
        json.loads(chunk[6:]) for chunk in chunks
        if json.loads(chunk[6:]).get("type") == "confirm_required"
    )
    pending = tool_executor._CONFIRM_STORE.records[
        tool_executor._token_hash(event["confirm_token"])
    ]

    assert captured_tools
    assert all(item["function"]["name"].startswith("cap__") for item in captured_tools)
    assert event["tool_name"] == tool.name
    assert pending["catalog_release"] == release.release_id
    assert pending["capability_id"] == tool.capability_id
    assert pending["major_version"] == tool.major_version
    assert pending["agent_identity"]["consumer"]["type"] == "agent"
    assert pending["agent_identity"]["consumer"]["agent_run_id"] == "run-1"
    assert pending["idempotency_key"] == "request-1:call-1"


def test_chj_connection_test_does_not_require_litellm(monkeypatch):
    original_import = builtins.__import__
    monkeypatch.setattr(
        builtins,
        "__import__",
        lambda name, *args, **kwargs: (
            (_ for _ in ()).throw(ImportError("litellm is intentionally absent"))
            if name == "litellm" else original_import(name, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(ai_chat, "_get_ai_config", lambda *_args: {
        "model": "kivy-glm-5", "api_key": "key",
        "api_base": "http://api-hub.inner.chj.cloud/llm-gateway/v1",
    })
    monkeypatch.setattr(ai_chat, "_chj_completion", lambda **_kwargs: {
        "choices": [{"message": {"content": "ok"}}],
    })

    assert ai_chat.test_connection({}, {"gid": "user-1"}) == {
        "success": True, "reply": "ok", "model": "kivy-glm-5",
    }


def test_chj_http_failure_reports_sanitized_upstream_reason(monkeypatch):
    import httpx

    response = httpx.Response(
        500,
        json={
            "code": 5000000,
            "message": "系统异常",
            "data": "模型[GLM-5] Connect timed out for secret-key",
        },
        request=httpx.Request("POST", "http://api-hub.inner.chj.cloud"),
    )
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: response)

    with pytest.raises(RuntimeError) as exc_info:
        ai_chat._chj_completion(
            messages=[{"role": "user", "content": "reply: ok"}],
            model_id="kivy-glm-5",
            api_key="secret-key",
            max_tokens=16,
        )

    message = str(exc_info.value)
    assert "CHJ gateway HTTP 500" in message
    assert "Connect timed out" in message
    assert "secret-key" not in message
