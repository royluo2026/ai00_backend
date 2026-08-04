import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CraftWorkbenchBoundaryTests(unittest.TestCase):
    def test_base_workbench_is_only_a_compatibility_import(self):
        source = (ROOT / "backend/routers/workbench_home.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_", source)
        self.assertIn("plugins.craft.craft_backend.routers.workbench_home", source)

    def test_craft_workbench_has_no_base_sql(self):
        source = (ROOT / "plugins/craft/craft_backend/routers/workbench_home.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_auth_", source)
        self.assertNotIn("workmanship_know_entries", source)
        self.assertIn("list_knowledge_workbench_items", source)

    def test_knowledge_projection_is_base_owned(self):
        source = (ROOT / "backend/platform_sdk/knowledge.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_know_entries", source)
        self.assertNotIn("workmanship_proj_", source)
        self.assertNotIn("workmanship_bop_", source)


if __name__ == "__main__":
    unittest.main()
