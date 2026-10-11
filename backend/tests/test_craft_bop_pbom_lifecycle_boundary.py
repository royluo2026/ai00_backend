"""Gateway boundary tests for PBOM/BOP lifecycle reads."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from plugins.craft.craft_backend.routers._bop import lifecycle
from plugins.craft.craft_backend.capabilities import bop_pbom_lifecycle_read


def test_pbom_lifecycle_read_routes_are_gateway_bound():
    for name in ("get_pbom_link_stats", "get_pbom_diff_queue"):
        route = getattr(lifecycle, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.bop.pbom_lifecycle.read" in inspect.getsource(route)
    tree = ast.parse(Path(lifecycle.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"get_pbom_link_stats", "get_pbom_diff_queue"}:
            assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "get_conn" for item in ast.walk(node))


def test_pbom_link_statistics_exclude_soft_deleted_links(monkeypatch):
    class Connection:
        def __init__(self):
            self.calls = []
            self.rows = [
                {"meta": {"pbom_match": {"pbom_version_gid": "pbom-1"}}},
                {"cnt": 2}, {"cnt": 3},
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return self

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchone(self):
            return self.rows.pop(0)

    connection = Connection()
    monkeypatch.setattr(bop_pbom_lifecycle_read, "get_craft_conn", lambda: connection)
    result = bop_pbom_lifecycle_read.read_bop_pbom_lifecycle(
        {"operation": "link_stats", "gid": "v1"}, object()
    )
    assert result.data == {"linked": 2, "total": 3, "pbom_version_gid": "pbom-1"}
    assert connection.calls[1] == (
        "SELECT COUNT(DISTINCT entity_gid) AS cnt FROM workmanship_bop_bop_entry_links "
        "WHERE version_gid=%s AND link_type='pbom_part' AND is_deleted=FALSE",
        ("v1",),
    )


def test_legacy_pbom_stats_cannot_probe_foreign_schema_or_count_deleted_links():
    source = Path(lifecycle.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    legacy = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_legacy_get_pbom_link_stats")
    body = ast.get_source_segment(source, legacy)
    assert "information_schema" not in body
    assert "ref_gid" not in body
    assert "is_deleted=FALSE" in body
