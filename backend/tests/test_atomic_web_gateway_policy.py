from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.reliability import (
    ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter,
    ReliabilityCoordinator,
)


def _specs():
    from backend.base.web_atomic import register_atomic_web_capabilities

    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    return {item.spec.id: item.spec for item in registry.snapshot()}


def test_atomic_permissions_reuse_legacy_role_boundaries_not_broad_domain_flags():
    specs = _specs()
    assert set(specs) == {
        "base.authorization.grant.list",
        "base.authorization.grant.create",
        "base.authorization.grant.revoke",
        "base.notification.preference.atomic.get",
        "base.notification.preference.atomic.update",
        "base.identity.directory.feishu.sync",
        "base.plugin.installed.list",
        "base.identity.user.search",
        "base.organization.team.directory.list",
        "base.team.directory.list",
        "base.self_annotation.batch.get",
        "base.identity.admin_user.list",
        "base.identity.role.assign.atomic",
    }
    for capability_id in {
        "base.authorization.grant.list",
        "base.authorization.grant.create",
        "base.authorization.grant.revoke",
    }:
        assert specs[capability_id].permissions == ("system.user.manage",)
    assert specs["base.identity.directory.feishu.sync"].permissions == (
        "system.tech_config",
    )
    for capability_id in {
        "base.notification.preference.atomic.get",
        "base.notification.preference.atomic.update",
        "base.plugin.installed.list",
        "base.identity.user.search",
        "base.organization.team.directory.list",
        "base.team.directory.list",
        "base.self_annotation.batch.get",
    }:
        assert specs[capability_id].permissions == ()
    for capability_id in {"base.identity.admin_user.list", "base.identity.role.assign.atomic"}:
        assert specs[capability_id].permissions == ("system.user.manage",)


def test_build_profile_grants_exact_coarse_role_matrix(monkeypatch):
    from backend.routers import deps

    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    profiles = {
        role: deps.build_profile(
            {"gid": role, "system_role": role, "org_role": "super_admin" if role == "super_admin" else "member", "is_active": True}
        )
        for role in ("super_admin", "team_admin", "member")
    }
    assert "system.user.manage" in profiles["super_admin"]["permissions"]
    assert "system.user.manage" in profiles["team_admin"]["permissions"]
    assert "system.user.manage" not in profiles["member"]["permissions"]
    assert "system.tech_config" in profiles["super_admin"]["permissions"]
    assert "system.tech_config" not in profiles["team_admin"]["permissions"]
    assert "system.tech_config" not in profiles["member"]["permissions"]


def _identity(role: str, *, service: bool = False) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id=None if service else role,
            service_id="service" if service else None,
            authentication_method="jwt",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(
            tenant_id="tenant_1", membership="member", active_roles=(role,)
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )


def _gateway(capability_id: str, users: dict, *, approvals=None, reliability=None):
    from backend.base.web_atomic import register_atomic_web_capabilities
    from backend.routers.deps import build_capability_authorization_grants

    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    provider = registry.get(capability_id)
    release = build_release([provider.descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda user_id: users.get(user_id),
        grants_resolver=lambda identity, user: build_capability_authorization_grants(
            user, identity.tenant.tenant_id
        ),
        approval_service=approvals,
    )
    return CapabilityGatewayService(
        CatalogResolver(store, registry), policy, reliability=reliability
    ).bind_release(release.release_id)


def _envelope(gateway, capability_id: str, role: str, payload: dict, *, service=False, key=None, approval=None):
    return InvocationEnvelope(
        capability_id=capability_id,
        major_version=1,
        catalog_release=gateway.catalog_release,
        payload=payload,
        identity=_identity(role, service=service),
        request_id=f"request_{role}",
        trace_id=f"trace_{role}",
        idempotency_key=key,
        approval_reference=approval,
    )


def test_production_gateway_role_matrix_for_authenticated_and_grant_manager_reads(monkeypatch):
    from backend.base import grant_service, plugin_inventory
    from backend.routers import deps

    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    monkeypatch.setattr(plugin_inventory, "list_installed_plugins", lambda: {"success": True, "data": []})
    monkeypatch.setattr(grant_service, "list_grants", lambda **_kwargs: {"grants": []})
    users = {
        role: {"gid": role, "system_role": role, "org_role": "super_admin" if role == "super_admin" else "member", "is_active": True}
        for role in ("super_admin", "team_admin", "member")
    }

    public_gateway = _gateway("base.plugin.installed.list", users)
    for role in users:
        assert asyncio.run(public_gateway.invoke(_envelope(public_gateway, "base.plugin.installed.list", role, {}))).ok
    unauthorized = asyncio.run(public_gateway.invoke(_envelope(public_gateway, "base.plugin.installed.list", "member", {}, service=True)))
    assert unauthorized.error.code == "service_authorization_unavailable"

    manager_gateway = _gateway("base.authorization.grant.list", users)
    assert asyncio.run(manager_gateway.invoke(_envelope(manager_gateway, "base.authorization.grant.list", "super_admin", {"user_gid": None}))).ok
    assert asyncio.run(manager_gateway.invoke(_envelope(manager_gateway, "base.authorization.grant.list", "team_admin", {"user_gid": None}))).ok
    denied = asyncio.run(manager_gateway.invoke(_envelope(manager_gateway, "base.authorization.grant.list", "member", {"user_gid": None})))
    assert denied.error.code == "permission_denied"


def test_production_gateway_super_admin_write_confirmation_and_member_denial(monkeypatch):
    from backend.services import org_sync_service
    from backend.routers import deps

    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    monkeypatch.setattr(org_sync_service, "sync_all_from_feishu", lambda **_kwargs: {
        "created": 0, "updated": 0, "dept_synced": 0,
        "departments": 0, "manual_teams_preserved": True,
    })
    users = {
        role: {"gid": role, "system_role": role, "org_role": "super_admin" if role == "super_admin" else "member", "is_active": True}
        for role in ("super_admin", "team_admin", "member")
    }
    approvals = ApprovalService(InMemoryApprovalStore())
    reliability = ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100))
    gateway = _gateway("base.identity.directory.feishu.sync", users, approvals=approvals, reliability=reliability)
    payload = {"department_id": None}
    denied = asyncio.run(gateway.invoke(_envelope(gateway, "base.identity.directory.feishu.sync", "member", payload, key="member-key")))
    assert denied.error.code == "permission_denied"
    challenge = asyncio.run(gateway.request_approval(_envelope(gateway, "base.identity.directory.feishu.sync", "super_admin", payload, key="sync-key")))
    result = asyncio.run(gateway.invoke(_envelope(gateway, "base.identity.directory.feishu.sync", "super_admin", payload, key="sync-key", approval=challenge.token)))
    assert result.ok
    assert result.data["manual_teams_preserved"] is True


def test_production_gateway_rejects_malformed_typed_provider_output(monkeypatch):
    from backend.base import plugin_inventory
    from backend.routers import deps

    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    monkeypatch.setattr(plugin_inventory, "list_installed_plugins", lambda: {"success": True, "data": [{"plugin_id": "p"}]})
    user = {"gid": "member", "system_role": "member", "org_role": "member", "is_active": True}
    gateway = _gateway("base.plugin.installed.list", {"member": user})
    result = asyncio.run(gateway.invoke(_envelope(gateway, "base.plugin.installed.list", "member", {})))
    assert result.ok is False
    assert result.error.code == "provider_failed"


def test_external_write_replays_once_and_reports_unknown_after_outcome_failure(monkeypatch):
    from backend.platform_sdk import notification_preferences
    from backend.routers import deps

    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    calls = []

    def update(_user_gid, changes):
        calls.append(dict(changes))
        return {
            "scope_approved": True, "scope_rejected": True,
            "item_status": bool(changes.get("item_status", True)),
            "new_follower": True,
        }

    monkeypatch.setattr(notification_preferences, "update_notification_preferences", update)
    user = {"gid": "member", "system_role": "member", "org_role": "member", "is_active": True}
    approvals = ApprovalService(InMemoryApprovalStore())
    store = InMemoryOutcomeStore()
    gateway = _gateway(
        "base.notification.preference.atomic.update", {"member": user},
        approvals=approvals,
        reliability=ReliabilityCoordinator(store, InMemoryRateLimiter(limit=100)),
    )
    payload = {"preferences": {"item_status": False}}
    pending = _envelope(gateway, "base.notification.preference.atomic.update", "member", payload, key="prefs-key")
    approval = asyncio.run(gateway.request_approval(pending))
    approved = pending.model_copy(update={"approval_reference": approval.token})
    first = asyncio.run(gateway.invoke(approved))
    replay = asyncio.run(gateway.invoke(approved))
    assert first.ok and replay.ok
    assert calls == [{"item_status": False}]

    class FailingCompleteStore(InMemoryOutcomeStore):
        def complete(self, operation_id, result):
            raise RuntimeError("outcome store unavailable")

    failing_approvals = ApprovalService(InMemoryApprovalStore())
    failing_gateway = _gateway(
        "base.notification.preference.atomic.update", {"member": user},
        approvals=failing_approvals,
        reliability=ReliabilityCoordinator(FailingCompleteStore(), InMemoryRateLimiter(limit=100)),
    )
    pending = _envelope(failing_gateway, "base.notification.preference.atomic.update", "member", payload, key="prefs-fail")
    approval = asyncio.run(failing_gateway.request_approval(pending))
    unknown = asyncio.run(failing_gateway.invoke(pending.model_copy(update={"approval_reference": approval.token})))
    assert unknown.status.value == "outcome_unknown"
    assert unknown.error.code == "outcome_persistence_failed"
    assert calls == [{"item_status": False}, {"item_status": False}]


def test_structural_gateway_enforces_admin_boundary_and_write_confirmation(monkeypatch):
    from backend.base import structural_web
    from backend.routers import deps

    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    monkeypatch.setattr(structural_web, "list_admin_users", lambda *, actor: {
        "success": True, "data": [],
    })
    calls = []
    monkeypatch.setattr(structural_web, "assign_user_role", lambda **payload: (
        calls.append(payload) or {"success": True, "data": {
            "gid": payload["user_gid"], "name": "", "email": "", "avatar_url": "",
            "system_role": payload["new_role"], "org_role": "member",
            "external_subtype": None, "team_id": None, "is_active": True, "created_at": "",
        }}
    ))
    users = {
        role: {"gid": role, "system_role": role, "org_role": "super_admin" if role == "super_admin" else "member", "is_active": True}
        for role in ("super_admin", "team_admin", "member")
    }
    read_gateway = _gateway("base.identity.admin_user.list", users)
    assert asyncio.run(read_gateway.invoke(_envelope(read_gateway, "base.identity.admin_user.list", "super_admin", {}))).ok
    assert asyncio.run(read_gateway.invoke(_envelope(read_gateway, "base.identity.admin_user.list", "team_admin", {}))).ok
    denied = asyncio.run(read_gateway.invoke(_envelope(read_gateway, "base.identity.admin_user.list", "member", {})))
    assert denied.error.code == "permission_denied"
    anonymous = asyncio.run(read_gateway.invoke(_envelope(read_gateway, "base.identity.admin_user.list", "member", {}, service=True)))
    assert anonymous.error.code == "service_authorization_unavailable"

    approvals = ApprovalService(InMemoryApprovalStore())
    gateway = _gateway(
        "base.identity.role.assign.atomic", users, approvals=approvals,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100)),
    )
    payload = {"user_gid": "target", "new_role": "member", "external_subtype": None}
    pending = _envelope(gateway, "base.identity.role.assign.atomic", "super_admin", payload, key="role-key")
    challenge = asyncio.run(gateway.request_approval(pending))
    approved = pending.model_copy(update={"approval_reference": challenge.token})
    assert asyncio.run(gateway.invoke(approved)).ok
    assert asyncio.run(gateway.invoke(approved)).ok
    assert len(calls) == 1

    class FailingCompleteStore(InMemoryOutcomeStore):
        def complete(self, operation_id, result):
            raise RuntimeError("outcome store unavailable")

    failing_approvals = ApprovalService(InMemoryApprovalStore())
    failing_gateway = _gateway(
        "base.identity.role.assign.atomic", users, approvals=failing_approvals,
        reliability=ReliabilityCoordinator(FailingCompleteStore(), InMemoryRateLimiter(limit=100)),
    )
    failing_pending = _envelope(
        failing_gateway, "base.identity.role.assign.atomic", "super_admin", payload,
        key="role-outcome-fail",
    )
    failing_challenge = asyncio.run(failing_gateway.request_approval(failing_pending))
    failing_approved = failing_pending.model_copy(
        update={"approval_reference": failing_challenge.token}
    )
    unknown = asyncio.run(failing_gateway.invoke(failing_approved))
    replay = asyncio.run(failing_gateway.invoke(failing_approved))
    assert unknown.status.value == "outcome_unknown"
    assert unknown.error.code == "outcome_persistence_failed"
    assert replay.status.value == "outcome_unknown"
    assert len(calls) == 2
