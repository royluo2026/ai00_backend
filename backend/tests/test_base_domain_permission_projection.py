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
