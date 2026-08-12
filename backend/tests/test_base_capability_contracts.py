"""Acceptance contracts for the Base Platform capability provider."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.capability_v2.bootstrap import get_capability_registry
from backend.capabilities.models_next import CapabilityContext
from backend.base.operations import worker_health
from backend.plugin_platform.storage import _identity
from backend.domain_ports.operations import operations_registry
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService


STABLE_CAPABILITIES = {
    "identity.principal.search",
    "plugin.disable", "plugin.enable", "plugin.install", "plugin.revoke",
    "plugin.rollback", "plugin.storage.delete", "plugin.storage.get",
    "plugin.storage.list", "plugin.storage.put", "plugin.uninstall",
    "plugin.upgrade", "plugin.upgrade.finish", "semantic.context.get",
    "system.activity.search", "system.change_impact.preview",
    "system.job.cancel", "system.job.get", "system.lineage.get", "system.search",
    "system.worker.outbox.health",
}


def _registrations():
    capability_registry = get_capability_registry()
    return {item.spec.id: item for item in capability_registry.snapshot() if item.spec.id in STABLE_CAPABILITIES}


def test_all_stable_base_capabilities_have_native_open_contracts():
    registrations = _registrations()
    assert set(registrations) == STABLE_CAPABILITIES
    for capability_id, item in registrations.items():
        descriptor = item.descriptor
        assert descriptor is not None, capability_id
        assert descriptor.owner_domain == "base"
        assert descriptor.lifecycle_status == "stable"
        assert descriptor.exposure.plugin is True
        assert descriptor.exposure.agent is True
        assert descriptor.exposure.mcp is True
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert descriptor.output_schema["properties"]
        assert descriptor.agent_output_schema == descriptor.output_schema
        assert descriptor.domain_errors_complete is True
        assert descriptor.domain_errors
        assert item.spec.plugin_callable is True


def test_plugin_lifecycle_is_exposed_but_remains_admin_governed():
    registrations = _registrations()
    lifecycle = {capability_id for capability_id in STABLE_CAPABILITIES if capability_id.startswith("plugin.") and not capability_id.startswith("plugin.storage.")}
    for capability_id in lifecycle:
        descriptor = registrations[capability_id].descriptor
        assert descriptor.automation_level == "A0"
        assert descriptor.confirmation_policy == "admin"
        assert descriptor.authorization_policy == "base.v2:system.plugin.manage"
        assert descriptor.idempotency_policy == "required"
        assert descriptor.audit_policy == "high_risk"
        assert descriptor.required_auth_freshness_seconds > 0


def test_base_writes_have_replay_protection():
    registrations = _registrations()
    writes = {
        "plugin.disable", "plugin.enable", "plugin.install", "plugin.revoke",
        "plugin.rollback", "plugin.storage.delete", "plugin.storage.put",
        "plugin.uninstall", "plugin.upgrade", "plugin.upgrade.finish",
        "system.job.cancel",
    }
    for capability_id in writes:
        assert registrations[capability_id].descriptor.idempotency_policy == "required"


def test_worker_health_uses_a_public_operations_provider(monkeypatch):
    class OperationsProvider:
        owner = "knowledge"

        def health(self, _context):
            return {"outbox_counts": {"pending": 2}}

    previous = dict(operations_registry.providers)
    operations_registry.register(OperationsProvider())
    monkeypatch.setattr(
        "backend.base.operations._base_health",
        lambda: {"heartbeat": None, "open_alerts": 1},
    )
    try:
        assert worker_health({}, CapabilityContext(user_gid="u1"))["open_alerts"] == 1
    finally:
        operations_registry.providers.clear()
        operations_registry.providers.update(previous)


def test_agent_may_use_an_explicitly_delegated_plugin_storage_namespace():
    context = CapabilityContext(user_gid="u1", team_gid="t1", source="agent", plugin_id="acme.tool")
    assert _identity(context) == ("t1", "acme.tool")


def test_storage_namespace_fails_closed_without_a_server_derived_consumer_id():
    import pytest

    with pytest.raises(PermissionError, match="authorized plugin context"):
        _identity(CapabilityContext(user_gid="u1", team_gid="t1", source="agent"))
    with pytest.raises(PermissionError, match="authorized plugin context"):
        _identity(CapabilityContext(
            user_gid="u1", team_gid="t1", source="web", plugin_id="forged.plugin",
        ))


def test_gateway_derives_agent_storage_namespace_from_trusted_identity():
    envelope = InvocationEnvelope(
        capability_id="plugin.storage.get", major_version=1, catalog_release="rel_test",
        payload={"key": "state"}, request_id="request_1", trace_id="trace_1",
        identity=ConsumerIdentity(
            actor=ActorIdentity(
                user_id="u1", authentication_method="test", authenticated_at=datetime.now(UTC),
            ),
            tenant=TenantIdentity(tenant_id="t1", membership="member"),
            consumer=ConsumerDescriptor(
                type=ConsumerType.AGENT, consumer_id="agent.planner", agent_run_id="run_1",
            ),
        ),
    )
    context = CapabilityGatewayService._legacy_context(envelope)
    assert context.plugin_id == "agent.planner"
    assert _identity(context) == ("t1", "agent.planner")
