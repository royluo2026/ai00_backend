import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PersonalActivityOwnershipTests(unittest.TestCase):
    def test_project_follow_and_notification_tables_are_project_management_owned(self):
        registry = json.loads((ROOT / "backend/governance/domain_boundaries.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["table_overrides"]["workmanship_work_follows"], "project_management")
        self.assertEqual(registry["table_overrides"]["workmanship_work_notifications"], "project_management")

    def test_base_follow_router_does_not_query_craft_tables(self):
        source = (ROOT / "backend/routers/follows.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_proj_", source)
        self.assertNotIn("workmanship_tpl_", source)
        self.assertIn("get_follow_item_owner", source)

if __name__ == "__main__":
    unittest.main()
