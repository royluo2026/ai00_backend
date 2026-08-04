import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CraftIdentityBoundaryTests(unittest.TestCase):
    def test_craft_approval_and_promotion_have_no_auth_sql(self):
        for relative in (
            "plugins/craft/craft_backend/routers/approval.py",
            "plugins/craft/craft_backend/routers/promotion.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("workmanship_auth_", source, relative)

    def test_identity_lookup_is_base_owned(self):
        source = (ROOT / "backend/platform_sdk/identity.py").read_text(encoding="utf-8")
        self.assertIn("workmanship_auth_users", source)
        self.assertNotIn("workmanship_proj_", source)


if __name__ == "__main__":
    unittest.main()
