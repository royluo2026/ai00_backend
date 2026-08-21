from pathlib import Path

import pytest

from plugins.agent.agent_backend.application.service import AgentApplication


ROUTER = Path("plugins/agent/agent_backend/routers/ai_chat.py")


def test_abort_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert '"agent.interaction.cancel"' in source


def test_interaction_cancel_requires_session_before_provider_io() -> None:
    app = AgentApplication(repository=object(), session_repository=object())
    context = type("Ctx", (), {"user_gid": "u", "team_gid": "t", "active_roles": ()})()
    with pytest.raises(ValueError, match="session_gid is required"):
        app.invoke("agent.interaction.cancel", {}, context)
