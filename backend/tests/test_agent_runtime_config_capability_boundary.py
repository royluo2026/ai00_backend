from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from plugins.agent.agent_backend.application.service import AgentApplication
from plugins.agent.agent_backend.capabilities.descriptors import specs
from plugins.agent.agent_backend.capabilities.provider import descriptor_for


ROOT = Path(__file__).resolve().parents[2]


def test_admin_config_route_uses_runtime_config_capability():
    source = (ROOT / "plugins/agent/agent_backend/routers/ai_chat.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_admin_config")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "invoke_agent_capability" in names
    assert "agent.runtime.config.read" in literals
    assert "_pi_proxy" not in names
    assert "_get_ai_config" not in names


def test_runtime_config_application_delegates_to_repository():
    calls = []

    class Repository:
        def runtime_config(self, payload):
            calls.append(payload)
            return {"source": "pi_runtime", "model": "pi", "has_key": True, "key_preview": "", "is_admin": True}

    app = AgentApplication(Repository())
    context = SimpleNamespace(user_gid="u1", team_gid="t1", active_roles=("super_admin",))
    assert app.invoke("agent.runtime.config.read", {}, context)["source"] == "pi_runtime"
    assert calls[0]["owner_gid"] == "u1"


def test_runtime_config_read_does_not_require_write_evidence():
    spec = next(item for item in specs() if item.id == "agent.runtime.config.read")
    assert descriptor_for(spec).evidence_policy == "optional"
