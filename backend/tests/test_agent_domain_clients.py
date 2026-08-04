import unittest
from pathlib import Path


class AgentDomainClientTests(unittest.TestCase):
    def test_project_and_knowledge_tools_have_no_domain_database_fallback(self):
        root = Path(__file__).resolve().parents[2]
        files = [
            root / "plugins/agent/agent_backend/ai_assistant/tool_handlers/project_tools.py",
            root / "plugins/agent/agent_backend/ai_assistant/tool_handlers/knowledge_tools.py",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in files)
        self.assertNotIn("backend.db", text)
        self.assertNotIn("get_conn", text)
        self.assertNotIn("FROM workmanship_", text)
        self.assertNotIn("FROM bop.", text)
        self.assertNotIn("FROM knowledge.", text)
        self.assertIn("domain_http", text)


    def test_in_process_agent_adapter_cannot_bypass_write_confirmation(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / "backend/platform_sdk/capabilities.py").read_text(encoding="utf-8")
        self.assertIn('item.spec.confirmation != "none"', text)
        self.assertIn("requires an explicit confirmation token", text)
if __name__ == "__main__":
    unittest.main()
