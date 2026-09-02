from unittest.mock import patch

from backend.routers.deps import build_profile
from backend.routers import plugin_marketplace
from backend.platform_sdk.effective_identity import build_effective_profile


def test_member_can_see_plugin_market_without_manage_permission():
    user = {
        "gid": "member-1",
        "system_role": "member",
        "org_role": "member",
        "is_active": True,
    }
    with patch("backend.routers.deps._get_user_grants", return_value=[]):
        profile = build_profile(user)

    assert "plugin-market" in profile["visible_panels"]
    assert "system.plugin.manage" not in profile["permissions"]
    assert {
        "craft.read",
        "craft.write",
        "factory.read",
        "digital_model.use",
        "simulation.use",
    } <= set(profile["permissions"])
    assert "factory.write" not in profile["permissions"]


def test_super_admin_keeps_plugin_management_permission():
    user = {
        "gid": "admin-1",
        "system_role": "super_admin",
        "org_role": "super_admin",
        "is_active": True,
    }
    with patch("backend.routers.deps._get_user_grants", return_value=[]):
        profile = build_profile(user)

    assert "plugin-market" in profile["visible_panels"]
    assert "system.plugin.manage" in profile["permissions"]
    assert {"factory.read", "factory.write"} <= set(profile["permissions"])


def test_legacy_knowledge_permissions_project_to_capability_permissions():
    user = {
        "gid": "member-1",
        "system_role": "member",
        "org_role": "member",
        "is_active": True,
    }
    with patch("backend.routers.deps._get_user_grants", return_value=[]):
        rest_profile = build_profile(user)
    effective_profile = build_effective_profile(user, [])

    assert "knowledge.read" in rest_profile["permissions"]
    assert "knowledge.write" not in rest_profile["permissions"]
    assert "knowledge.read" in effective_profile["permissions"]
    assert "knowledge.write" not in effective_profile["permissions"]


def test_legacy_knowledge_manage_projects_write_in_both_identity_paths():
    user = {
        "gid": "team-admin-1",
        "system_role": "member",
        "org_role": "member",
        "is_active": True,
    }
    grants = [{"grant_type": "team_admin"}]
    with patch("backend.routers.deps._get_user_grants", return_value=grants):
        rest_profile = build_profile(user)
    effective_profile = build_effective_profile(user, grants)

    assert {"knowledge.read", "knowledge.write"} <= set(rest_profile["permissions"])
    assert {"knowledge.read", "knowledge.write"} <= set(effective_profile["permissions"])


def test_external_user_does_not_receive_factory_capabilities():
    user = {
        "gid": "external-1",
        "system_role": "external",
        "org_role": "external",
        "is_active": True,
    }
    with patch("backend.routers.deps._get_user_grants", return_value=[]):
        profile = build_profile(user)

    assert "factory.read" not in profile["permissions"]
    assert "factory.write" not in profile["permissions"]


def test_upgrade_health_uses_trusted_control_plane_callback(monkeypatch):
    captured = {}

    def fake_finish(payload, context):
        captured.update(payload=payload, user_gid=context.user_gid, team_gid=context.team_gid)
        return {"plugin_id": payload["plugin_id"], "state": "enabled"}

    monkeypatch.setattr(plugin_marketplace, "finish_plugin_upgrade", fake_finish)
    result = plugin_marketplace.complete_installation_upgrade(
        "devteam.demo",
        plugin_marketplace.UpgradeHealthRequest(healthy=True),
        {"gid": "admin-1", "team_id": "team-1"},
    )

    assert result == {"success": True, "data": {"plugin_id": "devteam.demo", "state": "enabled"}}
    assert captured == {
        "payload": {"plugin_id": "devteam.demo", "healthy": True},
        "user_gid": "admin-1",
        "team_gid": "team-1",
    }
