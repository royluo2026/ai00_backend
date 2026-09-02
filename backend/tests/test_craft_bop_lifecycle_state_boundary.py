"""Gateway boundary tests for aggregate BOP lifecycle state."""
from __future__ import annotations

import ast
import inspect
import json
from datetime import date, datetime
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import lifecycle
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities import bop_lifecycle_state


def test_lifecycle_state_route_is_gateway_bound():
    route = lifecycle.get_lifecycle
    assert inspect.iscoroutinefunction(route)
    assert "craft.bop.lifecycle.state.read" in inspect.getsource(route)
    tree = ast.parse(Path(lifecycle.__file__).read_text(encoding="utf-8"))
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.AsyncFunctionDef) and item.name == "get_lifecycle")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))


def test_lifecycle_state_output_contract_accepts_governed_projection():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    schema = dict(registry.get("craft.bop.lifecycle.state.read").descriptor.output_schema)
    output = {
        "lifecycle_phase": "init",
        "lifecycle_state": {"init": {"route": "blank", "checklist": {"version_created": True}}},
        "bop_name": "总装 BOP", "version_tag": "V1", "data_stage": "S0",
        "version_family_gid": "family-1", "stats": None, "line_stats": [],
        "history": [], "lines": [],
        "pbom_match": {"pbom_version_gid": "pbom-1", "unlinked_ignored": 0},
        "pbom_vpps_check": {"total": 3, "nok": 0, "ignored": 0},
        "family_lifecycle_phase": "init", "pbom_diff_queue_pending": 0,
        "vehicle_ops_prep": {"confirmed": 0, "skipped": 0, "total": 0},
        "all_versions_in_family": [],
    }

    validate_payload(schema, output, label="output")


def test_lifecycle_state_provider_returns_json_transport_safe_dates(monkeypatch):
    class Cursor:
        def __init__(self):
            self.row = None
            self.rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=()):
            self.row = None
            self.rows = []
            if "FROM workmanship_bop_bop_versions WHERE gid=" in sql:
                self.row = {
                    "lifecycle_phase": "init", "lifecycle_state": {}, "bop_name": "BOP",
                    "version_tag": "V1", "data_stage": "S0", "version_family_gid": "family-1", "meta": {},
                }
            elif "line_gid IS NULL" in sql:
                self.row = {"stats_snapshot_date": date(2026, 9, 1), "refreshed_at": datetime(2026, 9, 1, 8, 30)}
            elif "lifecycle_history" in sql:
                self.rows = [{"gid": "h1", "entered_at": datetime(2026, 9, 1, 9, 0), "confirmed_at": None}]
            elif "bop_version_families" in sql:
                self.row = {"lifecycle_phase": "init"}
            elif "bop_pbom_diff_queue" in sql:
                self.row = {"cnt": 0}
            elif "version_family_gid=%s OR gid=%s" in sql:
                self.rows = [{"gid": "v1", "archived_at": date(2026, 9, 1), "is_deleted": 0}]

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(bop_lifecycle_state, "get_craft_conn", lambda: Connection())

    result = bop_lifecycle_state.read_bop_lifecycle_state(
        {"version_gid": "v1"},
        object(),
    ).data

    assert result["stats"]["stats_snapshot_date"] == "2026-09-01"
    assert result["stats"]["refreshed_at"] == "2026-09-01T08:30:00"
    assert result["history"][0]["entered_at"] == "2026-09-01T09:00:00"
    assert result["all_versions_in_family"][0]["archived_at"] == "2026-09-01"
    json.dumps(result)
