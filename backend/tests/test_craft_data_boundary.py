import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins.craft.craft_backend.data import connection as craft_connection
from plugins.craft.craft_backend.data.connection import _params


ROOT = Path(__file__).resolve().parents[2]
CRAFT_ROOT = ROOT / "plugins" / "craft"


class _Connection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


class _Pool:
    def __init__(self, connection):
        self._connection = connection

    def connection(self):
        return self._connection


class CraftDataBoundaryTests(unittest.TestCase):
    def test_craft_connection_commits_successful_work(self):
        connection = _Connection()
        with patch.object(craft_connection, "_get_pool", return_value=_Pool(connection)):
            with craft_connection.get_craft_conn():
                pass

        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertEqual(connection.closes, 1)

    def test_craft_connection_rolls_back_failed_work(self):
        connection = _Connection()
        with patch.object(craft_connection, "_get_pool", return_value=_Pool(connection)):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                with craft_connection.get_craft_conn():
                    raise RuntimeError("boom")

        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)
        self.assertEqual(connection.closes, 1)

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
