import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SelfAnnotationsOceanBaseBoundaryTests(unittest.TestCase):
    def test_router_is_user_private_and_mysql_backed(self):
        source = (ROOT / "backend/routers/self_annotations.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_base_self_annotations", source)
        self.assertIn("get_current_user", source)
        self.assertNotIn("get_current_user_optional", source)
        self.assertNotIn("sqlite", source.lower())
        self.assertIn("ON DUPLICATE KEY UPDATE", source)

    def test_local_sqlite_has_no_runtime_ddl(self):
        source = (ROOT / "backend/db/local_sqlite.py").read_text(encoding="utf-8").upper()
        self.assertNotIn("CREATE TABLE", source)
        self.assertNotIn("ALTER TABLE", source)


if __name__ == "__main__":
    unittest.main()
