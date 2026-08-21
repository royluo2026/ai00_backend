import unittest
import ast
from pathlib import Path


class AgentFlowBoundaryTests(unittest.TestCase):
    def test_flow_router_delegates_stable_outcomes_to_capability_gateway(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / "plugins/agent/agent_backend/routers/flows.py").read_text(encoding="utf-8")
        self.assertNotIn("backend.db", text)
        self.assertNotIn("backend.routers.deps", text)
        self.assertNotIn("app.flows", text)
        self.assertIn("invoke_agent_capability", text)
        self.assertNotIn("get_agent_conn", text)
        self.assertNotIn("cur.execute", text)
        self.assertIn("AI00_AGENT_DB_URL", (root / "plugins/agent/agent_backend/data/connection.py").read_text(encoding="utf-8"))
        self.assertNotIn("system_config", text)

    def test_script_generation_route_uses_governed_capability(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "plugins/agent/agent_backend/routers/flows.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "gen_script")
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertIn("invoke_agent_capability", names)
        self.assertIn("agent.script.generate", literals)
        self.assertNotIn("anthropic", names)
        self.assertNotIn("AsyncAnthropic", names)

    def test_script_generation_application_delegates_to_repository(self):
        from types import SimpleNamespace
        from plugins.agent.agent_backend.application.service import AgentApplication

        calls = []

        class Repository:
            def generate_script(self, payload):
                calls.append(payload)
                return {"success": True, "code": "return inputs"}

        app = AgentApplication(Repository())
        context = SimpleNamespace(user_gid="u1", team_gid="t1", active_roles=())
        payload = {"description": "copy inputs", "inputs_schema": {}, "outputs_schema": {}}
        self.assertEqual(app.invoke("agent.script.generate", payload, context), {"success": True, "code": "return inputs"})
        self.assertEqual(calls[0]["owner_gid"], "u1")


if __name__ == "__main__":
    unittest.main()
