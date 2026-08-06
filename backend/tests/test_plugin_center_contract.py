import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from backend.plugin_platform.service import list_releases


class _Cursor:
    def __init__(self, rows): self.rows, self.sql, self.params = rows, "", None
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()): self.sql, self.params = sql, params
    def fetchall(self): return self.rows


class _Connection:
    def __init__(self, rows): self.value = _Cursor(rows)
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.value


class PluginCenterContractTests(unittest.TestCase):
    def test_admin_release_queue_filters_and_sanitizes(self):
        rows = [{"plugin_id":"acme.demo","version":"1.0.0","manifest":'{"name":"Demo"}',"created_at":datetime(2026,7,1),"updated_at":datetime(2026,7,2)}]
        connection = _Connection(rows)
        module = types.ModuleType("backend.db.connection")
        module.get_conn = lambda: connection
        with patch.dict(sys.modules, {"backend.db.connection": module}):
            result = list_releases("submitted")
        self.assertEqual(connection.value.params, ("submitted",))
        self.assertEqual(result[0]["manifest"]["name"], "Demo")
        self.assertEqual(result[0]["updated_at"], "2026-07-02T00:00:00")
        with self.assertRaises(ValueError): list_releases("unknown")

    def test_web_center_has_three_tabs_and_core_metrics(self):
        root = Path(__file__).resolve().parents[2]
        workspace = root.parents[1] if root.parent.name == ".worktrees" else root.parent
        html = (workspace / "workmanship-web/web/settings/index.html").read_text(encoding="utf-8")
        js = (workspace / "workmanship-web/web/settings/plugin_center.js").read_text(encoding="utf-8")
        for tab in ("available", "installed", "upload"):
            self.assertIn(f'data-tab="{tab}"', html)
        for label in ("本月", "上月", "增量", "成功率"):
            self.assertIn(label, js)

    def test_usage_migration_enforces_normalized_deduplication_and_closure(self):
        root = Path(__file__).resolve().parents[2]
        sql = (root / "backend/db/migrations/202608040002_base_plugin_usage_metrics.sql").read_text(encoding="utf-8")
        self.assertIn("dedupe_key CHAR(64) PRIMARY KEY", sql)
        self.assertIn("workmanship_plugin_usage_month_closures", sql)
        self.assertIn("PRIMARY KEY (tenant_gid, plugin_id, month_start)", sql)


if __name__ == "__main__":
    unittest.main()
