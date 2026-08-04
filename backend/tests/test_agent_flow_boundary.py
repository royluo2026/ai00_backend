import unittest
from pathlib import Path


class AgentFlowBoundaryTests(unittest.TestCase):
    def test_flow_router_uses_agent_connection_and_owner_predicates(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / "plugins/agent/agent_backend/routers/flows.py").read_text(encoding="utf-8")
        self.assertNotIn("backend.db", text)
        self.assertNotIn("backend.routers.deps", text)
        self.assertNotIn("app.flows", text)
        self.assertIn("owner_user_gid=%s", text)
        self.assertIn("AI00_AGENT_DB_URL", (root / "plugins/agent/agent_backend/data/connection.py").read_text(encoding="utf-8"))
        self.assertIn("ANTHROPIC_API_KEY", text)
        self.assertNotIn("system_config", text)


if __name__ == "__main__":
    unittest.main()
