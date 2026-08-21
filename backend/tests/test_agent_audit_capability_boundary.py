from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from plugins.agent.agent_backend.application.service import AgentApplication


ROOT = Path(__file__).resolve().parents[2]


def test_agent_audit_routes_use_gateway_capabilities():
    source = (ROOT / "plugins/agent/agent_backend/routers/ai_audit.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for name, capability_id in (
        ("record_audit", "agent.audit.record"),
        ("list_audit_logs", "agent.audit.read"),
    ):
        function = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert "AuditRepository" not in names
        assert "_repository" not in names
        assert capability_id in literals


def test_agent_application_routes_audit_to_audit_repository():
    calls = []

    class ResourceRepository:
        pass

    class AuditRepository:
        def record(self, event):
            calls.append(("record", event))
            return "audit-1"

        def list(self, **kwargs):
            calls.append(("list", kwargs))
            return 1, [{"gid": "audit-1"}]

    app = AgentApplication(ResourceRepository(), AuditRepository())
    context = SimpleNamespace(user_gid="u1", team_gid="t1", active_roles=("super_admin",))

    assert app.invoke("agent.audit.record", {"tool_name": "bop.read"}, context) == {"gid": "audit-1"}
    assert app.invoke("agent.audit.read", {"limit": 20, "offset": 5}, context) == {
        "logs": [{"gid": "audit-1"}], "total": 1, "limit": 20, "offset": 5,
    }
    assert calls[0][1]["user_gid"] == "u1"


def test_unsupported_ai_balance_route_is_explicitly_retired():
    source = (ROOT / "plugins/agent/agent_backend/routers/ai_audit.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_ai_balance")
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
