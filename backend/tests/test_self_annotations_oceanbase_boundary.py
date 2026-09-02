import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SelfAnnotationsOceanBaseBoundaryTests(unittest.TestCase):
    def test_router_is_user_private_and_mysql_backed(self):
        source = (ROOT / "backend/routers/self_annotations.py").read_text(encoding="utf-8")
        owner = (ROOT / "backend/base/self_annotations.py").read_text(encoding="utf-8")
        self.assertIn("SelfAnnotationService", source)
        self.assertIn("workmanship_base_self_annotations", owner)
        self.assertIn("get_current_user", source)
        self.assertNotIn("get_current_user_optional", source)
        self.assertNotIn("sqlite", (source + owner).lower())
        self.assertIn("ON DUPLICATE KEY UPDATE", owner)

    def test_local_sqlite_has_no_runtime_ddl(self):
        source = (ROOT / "backend/db/local_sqlite.py").read_text(encoding="utf-8").upper()
        self.assertNotIn("CREATE TABLE", source)
        self.assertNotIn("ALTER TABLE", source)

    def test_state_join_is_collation_safe_during_rolling_migration(self):
        owner = (ROOT / "backend/base/self_annotations.py").read_text(encoding="utf-8")
        self.assertIn("s.tenant_gid COLLATE utf8mb4_unicode_ci=a.tenant_gid COLLATE utf8mb4_unicode_ci", owner)
        self.assertIn("s.item_gid COLLATE utf8mb4_unicode_ci=a.item_gid COLLATE utf8mb4_unicode_ci", owner)
        self.assertIn("s.user_gid COLLATE utf8mb4_unicode_ci=a.user_gid COLLATE utf8mb4_unicode_ci", owner)

    def test_collation_normalization_is_versioned(self):
        migration = ROOT / "backend/db/migrations/202609010002_base_self_annotation_collation.sql"
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE workmanship_base_self_annotations", sql)
        self.assertIn("ALTER TABLE workmanship_base_self_annotation_states", sql)
        self.assertGreaterEqual(sql.count("COLLATE utf8mb4_unicode_ci"), 6)


if __name__ == "__main__":
    unittest.main()
