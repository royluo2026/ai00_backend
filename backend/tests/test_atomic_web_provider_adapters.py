from __future__ import annotations

import asyncio

import pytest

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry


CTX = CapabilityContext(
    user_gid="usr_1",
    team_gid="team_1",
    active_roles=("team_admin",),
    permissions=("system.user.manage",),
)


def test_capability_and_rest_share_the_grant_owner_service(monkeypatch):
    from backend.base import grant_service, web_atomic
    from backend.routers import grants as grant_router

    calls = []

    def list_service(*, actor, user_gid=None):
        calls.append((actor["gid"], actor["system_role"], user_gid))
        return {"grants": []}

    monkeypatch.setattr(grant_service, "list_grants", list_service)
    assert web_atomic.invoke_atomic(
        "base.authorization.grant.list", {"user_gid": "usr_2"}, CTX
    ) == {"grants": []}
    assert grant_router.list_grants("usr_3", {"gid": "usr_1", "system_role": "team_admin"}) == {"grants": []}
    assert calls == [("usr_1", "team_admin", "usr_2"), ("usr_1", "team_admin", "usr_3")]


def test_provider_output_is_typed_and_rejected_when_service_shape_is_wrong(monkeypatch):
    from backend.base.web_atomic import register_atomic_web_capabilities

    class PluginService:
        def list_installed(self, *, actor):
            return {"installations": [{"plugin_id": "p"}]}
    monkeypatch.setattr("backend.plugin_platform.service.PluginPlatformService", PluginService)
    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    with pytest.raises(ValueError, match="missing required field"):
        asyncio.run(registry.invoke("base.plugin.installed.list", {}, CTX))


def test_super_admin_sync_guard_is_rechecked_inside_owner_provider(monkeypatch):
    from backend.services import org_sync_service
    from backend.base import web_atomic

    monkeypatch.setattr(org_sync_service, "sync_all_from_feishu", lambda **_kwargs: {
        "created": 0, "updated": 0, "dept_synced": 0,
        "departments": 0, "manual_teams_preserved": True,
    })
    member = CTX.model_copy(update={"active_roles": ("member",)})
    with pytest.raises(Exception, match="仅超管"):
        web_atomic.invoke_atomic("base.identity.directory.feishu.sync", {"department_id": None}, member)
    result = web_atomic.invoke_atomic(
        "base.identity.directory.feishu.sync",
        {"department_id": None},
        CTX.model_copy(update={"active_roles": ("super_admin",)}),
    )
    assert result == {
        "ok": True, "created": 0, "updated": 0, "dept_synced": 0,
        "departments": 0, "manual_teams_preserved": True,
    }


def test_grant_owner_service_enforces_scoped_team_admin_boundary(monkeypatch):
    from backend.base import grant_service

    actor = {"gid": "usr_scoped", "org_role": "member", "system_role": "member"}
    monkeypatch.setattr(grant_service, "_active_grants", lambda _gid: [{
        "grant_type": "team_admin",
        "scope_gid": "team_allowed",
    }])

    assert grant_service.can_manage(actor, "team_allowed") is True
    assert grant_service.can_manage(actor, "team_denied") is False
