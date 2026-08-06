import unittest
from pathlib import Path


class AgentKnowledgeCitationTests(unittest.TestCase):
    def test_agent_exposes_revision_tool_and_preserves_evidence(self):
        root = Path(__file__).resolve().parents[2]
        plugin = root / "plugins/agent/agent_backend/ai_assistant"
        registry = (plugin / "tool_registry.py").read_text(encoding="utf-8")
        adapter = (plugin / "tool_handlers/capability_tools.py").read_text(encoding="utf-8")
        prompt = (plugin / "system_prompt.py").read_text(encoding="utf-8")
        self.assertIn('"name": "get_knowledge_document"', registry)
        self.assertIn('"knowledge.document.get"', adapter)
        self.assertIn('invocation.get("evidence", [])', adapter)
        self.assertIn("来源:", prompt)
        self.assertIn('citation.get("digest"', prompt)


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
