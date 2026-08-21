import ast
import unittest
from pathlib import Path


class KnowledgeHubAccessBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.path = root / "plugins/knowledge/knowledge_backend/api/knowledge_hub_legacy.py"
        cls.repository_path = root / "plugins/knowledge/knowledge_backend/infrastructure/repository.py"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.repository_text = cls.repository_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text)

    def _function(self, name: str) -> str:
        node = next(item for item in self.tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
        return ast.get_source_segment(self.text, node) or ""

    def test_read_routes_apply_user_and_team_visibility(self):
        for name in ("list_items", "get_item", "get_item_history"):
            self.assertIn("_invoke", self._function(name), name)
        self.assertIn("_invoke", self._function("list_folders"))
        for name in ("list_favorites", "list_recent"):
            self.assertIn("_invoke", self._function(name), name)
        self.assertIn("scope_type='personal'", self.repository_text)
        self.assertIn("scope_type='team'", self.repository_text)

    def test_mutations_check_scope_ownership(self):
        for name in ("patch_item", "delete_item"):
            self.assertIn("_invoke", self._function(name), name)
        for name in ("create_folder", "patch_folder", "delete_folder"):
            self.assertIn("_invoke", self._function(name), name)
        self.assertIn("Cannot access another team", self.repository_text)
        self.assertIn("Public knowledge requires knowledge.manage", self.repository_text)

    def test_favorite_and_recent_cannot_create_visibility_bypass(self):
        for name in ("toggle_favorite", "record_recent"):
            self.assertIn("_invoke", self._function(name), name)

    def test_moves_validate_target_folder_boundary(self):
        source = self.repository_text
        self.assertIn("def item_update", source)
        self.assertIn("self._legacy_mutable(dict(folder)", source)
        self.assertIn("Folder scope mismatch", source)
        folder_repo = self.repository_text
        self.assertIn("def folder_update", folder_repo)
        self.assertIn("self._legacy_mutable(dict(parent)", folder_repo)
        self.assertIn("Parent folder scope mismatch", folder_repo)

    def test_explicit_null_move_to_root_is_not_treated_as_omitted(self):
        folder = self._function("patch_folder")
        item = self._function("patch_item")
        self.assertIn("model_dump(exclude_unset=True)", folder)
        self.assertIn("model_dump(exclude_unset=True)", item)

    def test_scope_change_is_not_a_silent_partial_update(self):
        self.assertIn("Knowledge item scope is immutable", self.repository_text)
    def test_destructive_folder_delete_avoids_recursive_cte(self):
        source = self.repository_text
        self.assertNotIn("WITH RECURSIVE", source.upper())
        self.assertIn("frontier", source)
        self.assertIn("self._legacy_mutable(dict(item)", source)

    def test_omitted_scope_defaults_to_personal(self):
        self.assertGreaterEqual(self.text.count('scope_type: str = "personal"'), 2)


if __name__ == "__main__":
    unittest.main()
