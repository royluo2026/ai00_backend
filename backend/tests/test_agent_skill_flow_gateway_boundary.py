from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_flow_router_has_no_database_access_and_uses_agent_capability_adapter() -> None:
    text = (ROOT / "plugins/agent/agent_backend/routers/flows.py").read_text(encoding="utf-8")

    assert "get_agent_conn" not in text
    assert "cur.execute" not in text
    assert "invoke_agent_capability" in text


def test_skill_router_has_no_database_access_and_uses_agent_capability_adapter() -> None:
    text = (ROOT / "plugins/agent/agent_backend/routers/skills_v2.py").read_text(encoding="utf-8")

    assert "get_agent_conn" not in text
    assert "cur.execute" not in text
    assert "invoke_agent_capability" in text
