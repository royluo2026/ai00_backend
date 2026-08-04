import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CRAFT = ROOT / "plugins" / "craft" / "craft_backend"


class CraftVppsAuditBoundaryTests(unittest.TestCase):
    def test_router_uses_craft_owned_vpps_domain(self):
        source = (CRAFT / "routers" / "vpps_audit.py").read_text(encoding="utf-8")
        self.assertNotIn("backend.domain.vpps_audit", source)
        self.assertNotIn("backend.infra.vpps_audit", source)
        self.assertIn("MySqlVppsOperationRepository", source)

    def test_repository_uses_oceanbase_mysql_dialect(self):
        source = (CRAFT / "vpps_audit" / "mysql_repository.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_bop_vpps_operations", source)
        self.assertIn("INSERT IGNORE", source)
        self.assertNotIn("ON CONFLICT", source)
        self.assertNotIn("RETURNING", source)


if __name__ == "__main__":
    unittest.main()
