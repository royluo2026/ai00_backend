from pathlib import Path

import pytest

from plugins.agent.agent_backend.application.service import AgentApplication


ROUTER = Path("plugins/agent/agent_backend/routers/ai_chat.py")


def test_tool_catalog_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert '"agent.tool_catalog.read"' in source


def test_tool_catalog_is_read_only_contract() -> None:
    assert "agent.tool_catalog.read".endswith(".read")


def test_unknown_agent_tool_catalog_payload_does_not_require_database() -> None:
    app = AgentApplication(repository=object())
    with pytest.raises(ValueError, match="unsupported tool catalog operation"):
        app.invoke("agent.tool_catalog.read", {"operation": "write"}, type("Ctx", (), {"user_gid": "u", "team_gid": "t", "active_roles": ()})())
