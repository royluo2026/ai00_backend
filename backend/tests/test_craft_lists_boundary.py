import unittest
from pathlib import Path


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

    def test_access_projection_is_base_owned(self):
        source = (ROOT / "backend/platform_sdk/access.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_auth_project_members", source)
        self.assertIn("workmanship_auth_users", source)


if __name__ == "__main__":
    unittest.main()
