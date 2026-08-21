import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CraftImportExportBoundaryTests(unittest.TestCase):
    def test_craft_import_export_does_not_own_base_template_storage(self):
        source = (ROOT / "plugins/craft/craft_backend/routers/import_export.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_app_export_templates", source)
        self.assertNotIn("backend.platform_sdk.export_templates", source)

    def test_export_template_sql_is_base_owned(self):
        source = (ROOT / "backend/platform_sdk/export_templates.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_app_export_templates", source)
        self.assertNotIn("workmanship_bop_", source)
        self.assertNotIn("workmanship_proj_", source)


if __name__ == "__main__":
    unittest.main()
