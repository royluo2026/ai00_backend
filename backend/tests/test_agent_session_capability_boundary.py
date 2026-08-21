from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from plugins.agent.agent_backend.application.service import AgentApplication


ROOT = Path(__file__).resolve().parents[2]


def test_agent_session_routes_use_gateway_capabilities():
    source = (ROOT / "plugins/agent/agent_backend/routers/ai_chat.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    expected = {
        "list_sessions": "agent.session.read",
        "get_session": "agent.session.read",
        "new_session": "agent.session.change.apply",
        "delete_session": "agent.session.change.apply",
    }
    for name, capability_id in expected.items():
        function = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert "_store" not in names
        assert "_pi_proxy" not in names
        assert capability_id in literals


def test_agent_application_routes_session_operations_to_session_repository():
    calls = []

    class ResourceRepository:
        pass

    class AuditRepository:
        pass

    class SessionRepository:
        def list_sessions(self, user_gid):
            calls.append(("list", user_gid))
            return [{"gid": "s1"}]

        def get_session(self, session_gid, user_gid):
            calls.append(("get", session_gid, user_gid))
            return [{"role": "user", "content": "hello"}]

        def create_session(self, user_gid):
            calls.append(("create", user_gid))
            return "s2"

        def delete_owned_session(self, session_gid, user_gid):
            calls.append(("delete", session_gid, user_gid))
            return True

    app = AgentApplication(ResourceRepository(), AuditRepository(), SessionRepository())
    context = SimpleNamespace(user_gid="u1", team_gid="t1", active_roles=())

    assert app.invoke("agent.session.read", {"operation": "list"}, context) == {"sessions": [{"gid": "s1"}]}
    assert app.invoke("agent.session.read", {"operation": "get", "session_gid": "s1"}, context) == {
        "turns": [{"role": "user", "content": "hello"}],
    }
    assert app.invoke("agent.session.change.apply", {"operation": "create"}, context) == {"session_gid": "s2"}
    assert app.invoke("agent.session.change.apply", {"operation": "delete", "session_gid": "s2"}, context) == {"success": True}
    assert calls == [
        ("list", "u1"), ("get", "s1", "u1"), ("create", "u1"), ("delete", "s2", "u1"),
    ]


def test_unsupported_admin_config_write_route_is_explicitly_retired():
    source = (ROOT / "plugins/agent/agent_backend/routers/ai_chat.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "save_admin_config")
    assert any(
        isinstance(decorator, ast.Call)
        and any(
            keyword.arg == "status_code"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == 410
            for keyword in decorator.keywords
        )
        for decorator in function.decorator_list
    )
