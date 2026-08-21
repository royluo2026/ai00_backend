from pathlib import Path

import pytest

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
