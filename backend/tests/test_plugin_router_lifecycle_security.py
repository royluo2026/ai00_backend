from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_rest_lifecycle_adapter_rejects_a_member_without_plugin_management_permission(monkeypatch):
    """Fails if a JWT-authenticated member can reach the lifecycle service directly."""
    from backend.routers import plugins

    monkeypatch.setattr(
        plugins, "build_profile",
        lambda _user: {"gid": "member_1", "team_id": "team_1", "permissions": []},
    )

    with pytest.raises(HTTPException) as exc:
        plugins._trusted_lifecycle_actor({"gid": "member_1", "team_id": "team_1"})

    assert exc.value.status_code == 403


def test_rest_lifecycle_adapter_uses_trusted_team_tenant_and_permission(monkeypatch):
    """Fails if the REST compatibility route forwards raw user fields rather than its trusted projection."""
    from backend.routers import plugins

    monkeypatch.setattr(
        plugins, "build_profile",
        lambda _user: {"gid": "admin_1", "team_id": "team_1", "permissions": ["system.plugin.manage"]},
    )

    assert plugins._trusted_lifecycle_actor({"gid": "admin_1", "team_id": "team_1"}) == {
        "gid": "admin_1", "tenant_gid": "team_1",
    }


def test_rest_install_route_denies_before_constructing_the_service(monkeypatch):
    from backend.routers import plugins

    monkeypatch.setattr(plugins, "build_profile", lambda _user: {"gid": "member_1", "permissions": []})
    monkeypatch.setattr(plugins, "PluginPlatformService", lambda: pytest.fail("service must not be constructed"))
    body = plugins.PluginInstallBody(
        plugin_id="devteam.example.plugin", release_version="1.2.3", release_sha256="sha256:" + "b" * 64,
        requested_grants=["project.read"], idempotency_key="key_1",
    )

    with pytest.raises(HTTPException) as exc:
        plugins.install_plugin(body, {"gid": "member_1"})
    assert exc.value.status_code == 403


def test_rest_install_route_passes_only_the_trusted_actor_projection(monkeypatch):
    from backend.routers import plugins

    received = {}

    class Service:
        def request_install(self, *, actor, command):
            received.update(actor=actor, command=command)
            return {"state": "disabled"}

    monkeypatch.setattr(
        plugins, "build_profile",
        lambda _user: {"gid": "admin_1", "team_id": "team_1", "permissions": ["system.plugin.manage"]},
    )
    monkeypatch.setattr(plugins, "PluginPlatformService", Service)
    body = plugins.PluginInstallBody(
        plugin_id="devteam.example.plugin", release_version="1.2.3", release_sha256="sha256:" + "b" * 64,
        requested_grants=["project.read"], idempotency_key="key_1",
    )

    assert plugins.install_plugin(body, {"gid": "forged", "tenant_gid": "forged"})["success"] is True
    assert received["actor"] == {"gid": "admin_1", "tenant_gid": "team_1"}
