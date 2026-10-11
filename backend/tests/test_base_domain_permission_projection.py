from __future__ import annotations

import pytest

from backend.platform_sdk.effective_identity import build_effective_profile
from backend.routers import deps


def _profiles(monkeypatch: pytest.MonkeyPatch, role: str) -> tuple[set[str], set[str]]:
    user = {
        "gid": f"user-{role}",
        "system_role": role,
        "org_role": "super_admin" if role == "super_admin" else "member",
    }
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    rest = set(deps.build_profile(user)["permissions"])
    shared = set(build_effective_profile(user, [])["permissions"])
    return rest, shared


def test_super_admin_projects_full_base_domain_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    for permissions in _profiles(monkeypatch, "super_admin"):
        assert {"base.read", "base.write"} <= permissions


def test_team_admin_projects_base_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for permissions in _profiles(monkeypatch, "team_admin"):
        assert "base.read" in permissions
        assert "base.write" not in permissions


def test_member_does_not_gain_base_domain_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    for permissions in _profiles(monkeypatch, "member"):
        assert "base.read" not in permissions
        assert "base.write" not in permissions


@pytest.mark.parametrize("role", ["super_admin", "team_admin", "member", "external"])
@pytest.mark.parametrize("explicit_org_role", [True, False])
def test_agent_write_is_projected_only_for_organization_super_admin(monkeypatch, role, explicit_org_role):
    from backend.platform_sdk import project_access
    monkeypatch.setattr(project_access, "list_user_project_memberships", lambda _gid: [])
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    user = {"gid": "actor", "system_role": role}
    if explicit_org_role:
        user["org_role"] = deps._derive_org_role(role)
    profiles = [deps.build_profile(user), build_effective_profile(user, [])]
    grants = deps.build_capability_authorization_grants(user, "organization-1")
    for permissions in [*(profile["permissions"] for profile in profiles), grants.permissions]:
        assert ("agent.write" in permissions) == (role == "super_admin")
        assert ("agent.read" in permissions) == (role != "external")
