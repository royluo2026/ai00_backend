import ast
import unittest
from pathlib import Path


class KnowledgeHubAccessBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path(__file__).resolve().parents[1] / "routers/knowledge_hub.py"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text)

    def _function(self, name: str) -> str:
        node = next(item for item in self.tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
        return ast.get_source_segment(self.text, node) or ""

    def test_read_routes_apply_user_and_team_visibility(self):
        for name in ("list_folders", "list_items", "get_item", "get_item_history", "list_favorites", "list_recent"):
            self.assertIn("_visible_predicate", self._function(name), name)
        self.assertIn("scope_type='personal'", self.text)
        self.assertIn("scope_type='team'", self.text)

    def test_mutations_check_scope_ownership(self):
        for name in ("patch_folder", "delete_folder", "patch_item", "delete_item"):
            self.assertIn("_assert_mutable", self._function(name), name)
        self.assertIn("cannot access another team", self.text)
        self.assertIn("public knowledge requires knowledge.manage", self.text)

    def test_favorite_and_recent_cannot_create_visibility_bypass(self):
        for name in ("toggle_favorite", "record_recent"):
            self.assertIn("_visible_predicate", self._function(name), name)

    def test_moves_validate_target_folder_boundary(self):
        for name in ("patch_folder", "patch_item"):
            source = self._function(name)
            self.assertIn("_assert_mutable(dict(", source, name)
            self.assertIn("scope mismatch", source, name)

    def test_explicit_null_move_to_root_is_not_treated_as_omitted(self):
        folder = self._function("patch_folder")
        item = self._function("patch_item")
        self.assertIn('_field_was_set(body, "parent_gid")', folder)
        self.assertIn('sets.append("parent_gid = %s")', folder)
        self.assertIn('_field_was_set(body, "folder_gid")', item)
        self.assertIn('sets.append("folder_gid = %s")', item)

    def test_scope_change_is_not_a_silent_partial_update(self):
        source = self._function("patch_item")
        self.assertIn("knowledge item scope is immutable", source)
    def test_destructive_folder_delete_avoids_recursive_cte(self):
        source = self._function("delete_folder")
        self.assertNotIn("WITH RECURSIVE", source.upper())
        self.assertIn("frontier", source)
        self.assertIn("_assert_mutable(dict(item)", source)

    def test_omitted_scope_defaults_to_personal(self):
        self.assertGreaterEqual(self.text.count("str = 'personal'"), 2)


if __name__ == "__main__":
    unittest.main()