import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins.craft.craft_backend.data.connection import _params


ROOT = Path(__file__).resolve().parents[2]
CRAFT_ROOT = ROOT / "plugins" / "craft"


class CraftDataBoundaryTests(unittest.TestCase):
    def test_craft_requires_its_own_database_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AI00_CRAFT_DB_URL is required"):
                _params()

    def test_craft_does_not_import_base_database_or_auth_internals(self):
        forbidden = {"backend.db.connection", "backend.routers.deps", "backend.utils.gid"}
        for path in CRAFT_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in forbidden:
                    self.fail(f"{path}: forbidden import {node.module}")


if __name__ == "__main__":
    unittest.main()
