import sys
import types
import unittest
from datetime import date
from unittest.mock import patch

from backend.capabilities.models_next import CapabilityContext
from backend.plugin_platform import metrics as metrics_module
from backend.plugin_platform.metrics import _close_tenant_month, close_previous_month_all_tenants, monthly_ranking, next_month, parse_month, previous_month, usage_dedupe_key


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, _sql, _params): return None
    def fetchall(self): return self.rows


class _Connection:
    def __init__(self, rows): self.rows = rows
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return _Cursor(self.rows)


def _connection_module(rows):
    module = types.ModuleType("backend.db.connection")
    module.get_conn = lambda: _Connection(rows)
    return module


class PluginUsageMetricsTests(unittest.TestCase):
    def test_month_arithmetic(self):
        self.assertEqual(parse_month("2026-07"), date(2026, 7, 1))
        self.assertEqual(previous_month(date(2026, 1, 1)), date(2025, 12, 1))
        self.assertEqual(next_month(date(2026, 12, 1)), date(2027, 1, 1))
        with self.assertRaises(ValueError): parse_month("2026/07")

    def test_web_counts_requests_but_agent_deduplicates_a_run(self):
        web = CapabilityContext(user_gid="u1", team_gid="t1", source="plugin", request_id="req-1", plugin_id="acme.ai00.hello", plugin_version="1.0.0")
        self.assertNotEqual(usage_dedupe_key(web, "system.echo"), usage_dedupe_key(web.model_copy(update={"request_id": "req-2"}), "system.echo"))
        agent = CapabilityContext(user_gid="u1", team_gid="t1", source="agent", request_id="req-1", plugin_id="acme.ai00.hello", plugin_version="1.0.0", agent_run_id="run-1")
        self.assertEqual(usage_dedupe_key(agent, "system.echo"), usage_dedupe_key(agent, "plugin.storage.get"))
        with self.assertRaises(ValueError):
            usage_dedupe_key(CapabilityContext(user_gid="u1", source="agent", plugin_id="acme.ai00.hello"), "system.echo")

    def test_automatic_close_targets_previous_month_once_per_tenant(self):
        rows = [{"tenant_gid": "t1"}, {"tenant_gid": "t2"}]
        closed = lambda tenant, actor, month: {"tenant_gid":tenant,"month":month.strftime("%Y-%m"),"already_closed":tenant == "t2","plugins":1}
        with patch.dict(sys.modules, {"backend.db.connection": _connection_module(rows)}), patch.object(metrics_module, "_close_tenant_month", side_effect=closed) as closer:
            result = close_previous_month_all_tenants(today=date(2026, 8, 4))
        self.assertEqual(result, {"month":"2026-07","tenants":2,"newly_closed":1,"already_closed":1,"plugins":2})
        self.assertEqual(closer.call_count, 2)
        self.assertTrue(all(call.args[2] == date(2026, 7, 1) for call in closer.call_args_list))
    def test_monthly_ranking_contains_previous_and_delta(self):
        rows = [
            {"plugin_id": "a.plugin.one", "month_start": date(2026, 7, 1), "usage_count": 12, "attempt_count": 15, "success_rate": 0.8},
            {"plugin_id": "a.plugin.one", "month_start": date(2026, 6, 1), "usage_count": 7, "attempt_count": 8, "success_rate": 0.875},
            {"plugin_id": "b.plugin.two", "month_start": date(2026, 7, 1), "usage_count": 3, "attempt_count": 3, "success_rate": 1.0},
        ]
        with patch.dict(sys.modules, {"backend.db.connection": _connection_module(rows)}):
            result = monthly_ranking({"gid": "u1", "team_id": "t1"}, "2026-07")
        self.assertEqual(result["items"][0]["current_usage"], 12)
        self.assertEqual(result["items"][0]["previous_usage"], 7)
        self.assertEqual(result["items"][0]["monthly_delta"], 5)
        self.assertEqual(result["items"][0]["success_rate"], 0.8)


if __name__ == "__main__":
    unittest.main()