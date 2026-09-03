from __future__ import annotations

import asyncio
import ast
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.models_next import CapabilityOutput
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from plugins.agent.agent_backend.application.service import AgentApplication
from plugins.agent.agent_backend.capabilities import register_capabilities
from plugins.agent.agent_backend.capabilities.descriptors import specs
from plugins.agent.agent_backend.capabilities.provider import descriptor_for


ROOT = Path(__file__).resolve().parents[2]


def test_admin_config_route_uses_runtime_config_capability():
    source = (ROOT / "plugins/agent/agent_backend/routers/ai_chat.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_admin_config")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "invoke_agent_capability" in names
    assert "agent.runtime.config.read" in literals
    assert "_pi_proxy" not in names
    assert "_get_ai_config" not in names


def test_runtime_config_application_delegates_to_repository():
    calls = []

    class Repository:
        def runtime_config(self, payload):
            calls.append(payload)
            return {"source": "pi_runtime", "model": "pi", "has_key": True, "key_preview": "", "is_admin": True}

    app = AgentApplication(Repository())
    context = SimpleNamespace(user_gid="u1", team_gid="t1", active_roles=("super_admin",))
    assert app.invoke("agent.runtime.config.read", {}, context)["source"] == "pi_runtime"
    assert calls[0]["owner_gid"] == "u1"


def test_runtime_config_read_does_not_require_write_evidence():
    spec = next(item for item in specs() if item.id == "agent.runtime.config.read")
    assert descriptor_for(spec).evidence_policy == "optional"


def test_registered_runtime_config_handler_matches_its_output_contract(monkeypatch):
    monkeypatch.setenv("AI00_AGENT_RUNTIME_MODE", "pi")
    registry = CapabilityRegistry()
    register_capabilities(registry, canvas_runtime=None)
    provider = registry.get("agent.runtime.config.read", 1)
    value = provider.handler(
        {}, SimpleNamespace(user_gid="u1", team_gid="t1", active_roles=("super_admin",))
    )
    assert "data" not in value
    validate_payload(dict(provider.descriptor.output_schema), value, label="output")


def test_registered_write_handler_commits_agent_outbox_and_evidence_contract(monkeypatch):
    monkeypatch.setattr(
        "plugins.agent.agent_backend.capabilities.AgentCapabilityRepository.apply",
        lambda _self, _payload: {"resource_gid": "run-1"},
    )
    transactions = []

    class Transaction:
        def __init__(self): self.events = []; self.committed = False
        def record_outbox(self, *args): self.events.append(args)
        def commit(self): self.committed = True
        def rollback(self): pass
        def close(self): pass

    def transaction_factory():
        transaction = Transaction(); transactions.append(transaction); return transaction

    registry = CapabilityRegistry()
    register_capabilities(
        registry, canvas_runtime=None, transaction_factory=transaction_factory,
    )
    provider = registry.get("agent.run.change.apply", 1)

    assert provider.descriptor.consistency_policy == "eventual"
    assert provider.descriptor.evidence_policy == "required"
    value = provider.handler(
        {}, SimpleNamespace(
            user_gid="u1", team_gid="t1", request_id="req-1",
            active_roles=("super_admin",),
        ),
    )

    assert getattr(provider.handler, "__capability_transactional__", False) is False
    assert isinstance(value, CapabilityOutput)
    assert value.evidence
    assert transactions[0].committed is True
    assert transactions[0].events[0][0] == "agent.run.change.apply"
    validate_payload(dict(provider.descriptor.output_schema), value.data, label="output")


def test_real_gateway_commits_registered_agent_write_with_evidence(monkeypatch):
    monkeypatch.setattr(
        "plugins.agent.agent_backend.capabilities.AgentCapabilityRepository.apply",
        lambda _self, _payload: {"resource_gid": "run-1"},
    )
    transactions = []

    class Transaction:
        def __init__(self): self.events = []; self.committed = False
        def record_outbox(self, *args): self.events.append(args)
        def commit(self): self.committed = True
        def rollback(self): pass
        def close(self): pass

    def transaction_factory():
        transaction = Transaction(); transactions.append(transaction); return transaction

    registry = CapabilityRegistry()
    register_capabilities(
        registry, canvas_runtime=None, transaction_factory=transaction_factory,
    )
    provider = registry.get("agent.run.change.apply", 1)
    release = build_release([provider.descriptor])
    store = InMemoryCatalogStore(); store.publish(release)

    class Policy:
        def authorize(self, *_args): return None
        def approve(self, *_args): return None
        def project(self, _descriptor, _identity, data): return data

    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), Policy(),
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=10)),
    ).bind_release(release.release_id)
    result = asyncio.run(gateway.invoke(InvocationEnvelope(
        capability_id=provider.spec.id, major_version=provider.spec.version,
        catalog_release=release.release_id, payload={},
        identity=ConsumerIdentity(
            actor=ActorIdentity(user_id="u1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
            tenant=TenantIdentity(tenant_id="t1", membership="member"),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.agent"),
        ),
        request_id="req-write-1", trace_id="req-write-1", idempotency_key="idem-write-1",
    )))

    assert result.ok is True
    assert result.data["resource_gid"] == "run-1"
    assert result.evidence[0].kind == "agent.change"
    assert transactions[0].committed is True
    assert transactions[0].events


def test_write_cleanup_preserves_provider_error_when_rollback_also_fails(monkeypatch):
    original = ValueError("provider rejected input")
    monkeypatch.setattr(
        "plugins.agent.agent_backend.capabilities.AgentCapabilityRepository.apply",
        lambda _self, _payload: (_ for _ in ()).throw(original),
    )

    class Transaction:
        closed = False
        def rollback(self): raise RuntimeError("rollback failed")
        def close(self): self.closed = True

    transaction = Transaction()
    registry = CapabilityRegistry()
    register_capabilities(
        registry, canvas_runtime=None, transaction_factory=lambda: transaction,
    )

    with pytest.raises(ValueError, match="provider rejected input") as raised:
        registry.get("agent.run.change.apply", 1).handler(
            {}, SimpleNamespace(user_gid="u1", team_gid="t1", request_id="req-1"),
        )
    assert raised.value is original
    assert transaction.closed is True
