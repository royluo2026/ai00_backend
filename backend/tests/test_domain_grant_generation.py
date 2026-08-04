import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.generate_domain_grants import main


class DomainGrantGenerationTests(unittest.TestCase):
    def test_plugin_storage_is_granted_only_to_base_runtime(self):
        inventory = Path(__file__).resolve().parents[2] / "backend/governance/table_inventory.json"
        args = [
            "generate_domain_grants.py", "--inventory", str(inventory), "--database", "workmanship",
            "--account", "base=ai00_base", "--account", "craft=ai00_craft",
            "--account", "simulation=ai00_sim", "--account", "agent=ai00_agent",
            "--account", "device=ai00_device", "--include-revokes",
        ]
        output = io.StringIO()
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        sql = output.getvalue()
        table = "`workmanship`.`workmanship_plugin_namespace_kv`"
        self.assertIn(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO 'ai00_base'@'%';", sql)
        self.assertIn(f"REVOKE ALL PRIVILEGES ON {table} FROM 'ai00_craft'@'%';", sql)
        self.assertNotIn(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO 'ai00_craft'@'%';", sql)


if __name__ == "__main__":
    unittest.main()