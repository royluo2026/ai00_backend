import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CraftProjectsBoundaryTests(unittest.TestCase):
    def test_craft_projects_has_no_auth_sql(self):
        source = (ROOT / "plugins/craft/craft_backend/routers/projects.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_auth_", source)
        self.assertNotIn("scope_visible_clause", source)
        self.assertIn("backend.platform_sdk.project_access", source)

    def test_project_access_sql_is_base_owned(self):
        source = (ROOT / "backend/platform_sdk/project_access.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_auth_project_members", source)
        self.assertIn("workmanship_auth_permission_grants", source)
        self.assertNotIn("workmanship_proj_", source)
        self.assertNotIn("workmanship_bop_", source)


if __name__ == "__main__":
    unittest.main()
