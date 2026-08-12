import unittest
from pathlib import Path


class AgentKnowledgeCitationTests(unittest.TestCase):
    def test_agent_exposes_revision_tool_and_preserves_evidence(self):
        root = Path(__file__).resolve().parents[2]
        plugin = root / "plugins/agent/agent_backend/ai_assistant"
        adapter = (plugin / "catalog_tools.py").read_text(encoding="utf-8")
        self.assertIn("agent_output_schema or item.output_schema", adapter)
        self.assertIn("return await self.client.invoke", adapter)
        self.assertFalse(any((plugin / "tool_handlers").rglob("*.py")))


    def test_web_agent_stream_and_ui_preserve_structured_evidence(self):
        root = Path(__file__).resolve().parents[2]
        stream = (root / "plugins/agent/agent_backend/routers/ai_chat.py").read_text(encoding="utf-8")
        workspace = root.parents[1] if root.parent.name == ".worktrees" else root.parent
        web = (workspace / "workmanship-web/web/workbench/workbench.js").read_text(encoding="utf-8")
        css = (workspace / "workmanship-web/web/workbench/workbench.css").read_text(encoding="utf-8")
        self.assertIn('evt["evidence"]', stream)
        self.assertIn("Array.isArray(evt.evidence)", web)
        self.assertIn("引用来源", web)
        self.assertIn(".wb-fc-evidence", css)
if __name__ == "__main__":
    unittest.main()
