import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins.simulation.simulation_backend.data.connection import _params


ROOT = Path(__file__).resolve().parents[2]
SIM_ROOT = ROOT / "plugins" / "simulation"


class SimulationDomainBoundaryTests(unittest.TestCase):
    def test_simulation_requires_its_own_database_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AI00_SIMULATION_DB_URL is required"):
                _params()

    def test_simulation_does_not_import_base_internals(self):
        allowed = ("backend.contracts", "backend.platform_sdk")
        for path in SIM_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                if module and module.startswith("backend."):
                    self.assertTrue(module.startswith(allowed), f"{path}: forbidden import {module}")

    def test_simulation_never_reads_craft_tables(self):
        for path in SIM_ROOT.rglob("*.py"):
            self.assertNotIn("workmanship_bop_", path.read_text(encoding="utf-8"), str(path))


if __name__ == "__main__":
    unittest.main()
