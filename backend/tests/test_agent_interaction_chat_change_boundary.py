from pathlib import Path

import pytest

from backend.platform_sdk.effective_identity import build_effective_profile
from backend.routers import deps
from plugins.agent.agent_backend.capabilities.interaction_chat_change import apply_interaction_chat_change


ROUTER = Path("plugins/agent/agent_backend/routers/ai_chat.py")


def test_agent_chat_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="agent.interaction.chat.change.apply"') == 1
    for name in ("chat_stream", "chat_sync", "confirm_tool", "confirm_tool_sync"):
        assert f"def _legacy_{name}" in source


def test_agent_chat_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        import asyncio
        asyncio.run(apply_interaction_chat_change({"operation": "delete", "body": {}}, object()))


@pytest.mark.parametrize(
    ("system_role", "org_role"),
    (("member", "member"), ("super_admin", "super_admin")),
)
def test_internal_user_can_authorize_agent_chat(monkeypatch, system_role, org_role) -> None:
    user = {
        "gid": f"{system_role}-1",
        "system_role": system_role,
        "org_role": org_role,
        "is_active": True,
    }
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])

    assert "agent.interact" in deps.build_profile(user)["permissions"]
    assert "agent.interact" in build_effective_profile(user, [])["permissions"]


def test_external_user_cannot_authorize_agent_chat(monkeypatch) -> None:
    user = {
        "gid": "external-1",
        "system_role": "member",
        "org_role": "external",
        "is_active": True,
    }
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])

    assert "agent.interact" not in deps.build_profile(user)["permissions"]
    assert "agent.interact" not in build_effective_profile(user, [])["permissions"]
