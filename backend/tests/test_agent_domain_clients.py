import unittest
from pathlib import Path

from backend.platform_sdk.capabilities import invoke_capability_for_user


class AgentDomainClientTests(unittest.TestCase):
    def test_project_and_knowledge_tools_have_no_domain_database_fallback(self):
        root = Path(__file__).resolve().parents[2]
        files = [root / "plugins/agent/agent_backend/ai_assistant/catalog_tools.py"]
        text = "\n".join(path.read_text(encoding="utf-8") for path in files)
        self.assertNotIn("backend.db", text)
        self.assertNotIn("get_conn", text)
        self.assertNotIn("FROM workmanship_", text)
        self.assertNotIn("FROM bop.", text)
        self.assertNotIn("FROM knowledge.", text)
        self.assertIn("DomainCapabilityClient", text)
        self.assertFalse(any((root / "plugins/agent/agent_backend/ai_assistant/tool_handlers").rglob("*.py")))


    def test_in_process_agent_adapter_cannot_bypass_write_confirmation(self):
        with self.assertRaisesRegex(PermissionError, "trusted ConsumerIdentity or Agent delegation"):
            invoke_capability_for_user(
                "craft.bop.version.archive", {}, user_gid="forged-user", source="agent"
            )
if __name__ == "__main__":
    unittest.main()
