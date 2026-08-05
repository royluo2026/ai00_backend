import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class CraftListsBoundaryTests(unittest.TestCase):
    def test_base_lists_is_only_a_compatibility_import(self):
        source = (ROOT / "backend/routers/lists.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_", source)
        self.assertIn("plugins.craft.craft_backend.routers.lists", source)

    def test_craft_lists_has_no_auth_sql_or_optional_identity(self):
        source = (ROOT / "plugins/craft/craft_backend/routers/lists.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_auth_", source)
        self.assertNotIn("get_current_user_optional", source)
        self.assertIn("build_access_scope", source)

    def test_craft_task_visibility_uses_base_projection_not_auth_sql(self):
        source = (ROOT / "plugins/craft/craft_backend/routers/promotion.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_auth_", source)
        self.assertIn("build_access_scope", source)

    def test_task_scope_clause_contains_only_craft_columns_and_projected_values(self):
        from plugins.craft.craft_backend.routers.promotion import _task_scope_clauses

        scope = {
            "user_gid": "u1",
            "team_member_gids": ["u1", "u2"],
            "project_gids": ["p1"],
        }
        with patch(
            "plugins.craft.craft_backend.routers.promotion.build_access_scope",
            return_value=scope,
        ):
            clause, params = _task_scope_clauses({"gid": "u1"}, "t")
        self.assertNotIn("SELECT", clause.upper())
        self.assertNotIn("workmanship_auth_", clause)
        self.assertIn("t.project_gid", clause)
        self.assertEqual(params, ["u1", "u1", "u2", "p1"])

    def test_access_projection_is_base_owned(self):
        source = (ROOT / "backend/platform_sdk/access.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_auth_project_members", source)
        self.assertIn("workmanship_auth_users", source)


if __name__ == "__main__":
    unittest.main()
