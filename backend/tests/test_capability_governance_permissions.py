import asyncio

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_governance_test.provider import register_governance_capabilities
from backend.routers import deps


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_governance_capabilities(registry)
    return registry


def test_analyst_can_search_but_cannot_review():
    registry = _registry()
    analyst = CapabilityContext(user_gid="analyst", permissions=("system.capability.read",))

    assert asyncio.run(registry.invoke(
        "base.capability_registry.search", {"query": "capability"}, analyst,
    )).data["status"] == "completed"
    assert registry.get("base.capability_review.decide").spec.permissions == (
        "system.capability.read", "system.capability.analyze", "system.capability.govern",
    )


def test_capability_grants_are_explicit_and_do_not_cross_domains(monkeypatch):
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [
        {"grant_type": "capability_analyst", "scope_gid": None},
    ])

    profile = deps.build_profile({"gid": "analyst", "system_role": "member", "org_role": "member"})

    assert {"system.capability.read", "system.capability.analyze"} <= set(profile["permissions"])
    assert "system.capability.govern" not in profile["permissions"]
    assert "system.capability.release" not in profile["permissions"]


def test_super_admin_gets_governance_permissions_only_in_test_profile(monkeypatch):
    user = {"gid": "admin", "system_role": "super_admin", "org_role": "super_admin"}
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    monkeypatch.delenv("AI00_DEPLOYMENT_PROFILE", raising=False)
    assert "system.capability.release" not in deps.build_profile(user)["permissions"]

    monkeypatch.setenv("AI00_DEPLOYMENT_PROFILE", "test-governance")
    assert {
        "system.capability.read", "system.capability.analyze",
        "system.capability.govern", "system.capability.release",
    } <= set(deps.build_profile(user)["permissions"])
