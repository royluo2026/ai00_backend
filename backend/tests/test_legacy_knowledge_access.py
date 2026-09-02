import ast
import unittest
from pathlib import Path


class LegacyKnowledgeAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.router_text = (
            root / "plugins/knowledge/knowledge_backend/api/knowledge_entries_legacy.py"
        ).read_text(encoding="utf-8")
        cls.router_tree = ast.parse(cls.router_text)
        cls.capability_text = (root / "backend/capabilities/knowledge_next.py").read_text(encoding="utf-8")
        cls.repository_text = (
            root / "plugins/knowledge/knowledge_backend/infrastructure/repository.py"
        ).read_text(encoding="utf-8")

    def _function(self, name: str) -> str:
        node = next(
            item for item in self.router_tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
        )
        return ast.get_source_segment(self.router_text, node) or ""

    def test_read_endpoints_require_login_and_visibility(self):
        for name in ("list_knowledge_entries", "get_knowledge_entry"):
            source = self._function(name)
            self.assertIn("get_current_user", source)
            self.assertIn("_invoke_knowledge", source)
            self.assertNotIn("get_current_user_optional", source)

    def test_mutations_check_visibility_and_writability(self):
        for name in ("update_knowledge_entry", "delete_knowledge_entry"):
            source = self._function(name)
            self.assertIn("_invoke_knowledge", source)
            self.assertIn("write=True", source)
            self.assertNotIn("get_conn", source)

    def test_identity_access_uses_public_projection_not_auth_sql(self):
        self.assertNotIn("workmanship_auth_", self.router_text)
        self.assertNotIn("workmanship_auth_", self.capability_text)
        self.assertIn("get_active_team_member_gids", self.capability_text)

    def test_global_scope_requires_knowledge_management(self):
        self.assertIn('share_scope == "global"', self.repository_text)
        self.assertIn("Global knowledge requires knowledge.manage", self.repository_text)


if __name__ == "__main__":
    unittest.main()
