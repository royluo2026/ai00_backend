"""Gateway boundary tests for legacy BOP entry read routes."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from plugins.craft.craft_backend.routers._bop import entries


ROUTES = (
    "auto_link_preview",
    "get_link_summary",
    "resolve_gids",
    "search_pbom_parts",
    "list_pbom_snapshots",
    "get_line_operations",
    "get_version_history",
    "get_entry_history",
)


def test_legacy_entry_read_routes_are_gateway_bound():
    for name in ROUTES:
        route = getattr(entries, name)
        assert inspect.iscoroutinefunction(route)
        assert "craft.bop.entry.legacy_read" in inspect.getsource(route)

    tree = ast.parse(Path(entries.__file__).read_text(encoding="utf-8"))
    names = set(ROUTES)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names:
            assert not any(
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "get_conn"
                for item in ast.walk(node)
            )


def test_legacy_entry_read_capability_declared():
    from plugins.craft.craft_backend.capabilities.bop_entry_legacy_read import OPERATIONS

    assert set(OPERATIONS) == {
        "auto_link_preview",
        "link_summary",
        "resolve_gids",
        "pbom_search",
        "pbom_snapshots",
        "project_bop_lines",
        "line_operations",
        "version_history",
        "entry_history",
        "version_entries",
    }


def test_relation_routes_use_atomic_read_capabilities():
    assert "craft.bop.entry.relation.list" in inspect.getsource(entries.list_entry_links)
    assert "craft.bop.linked_entity.detail.get" in inspect.getsource(entries.get_entity_detail)
    assert "craft.bop.entry.legacy_read" not in inspect.getsource(entries.list_entry_links)
    assert "craft.bop.entry.legacy_read" not in inspect.getsource(entries.get_entity_detail)


def test_version_entries_rejects_unbounded_pages():
    from plugins.craft.craft_backend.capabilities.bop_entry_legacy_read import read_bop_entry_legacy

    with pytest.raises(ValueError, match="between 1 and 100"):
        read_bop_entry_legacy({"operation": "version_entries", "version_gid": "v1", "limit": 101}, None)


def test_version_entries_rejects_negative_offset():
    from plugins.craft.craft_backend.capabilities.bop_entry_legacy_read import read_bop_entry_legacy

    with pytest.raises(ValueError, match="non-negative"):
        read_bop_entry_legacy({"operation": "version_entries", "version_gid": "v1", "offset": -1}, None)


class _SummaryCursor:
    def __init__(self, links, existing, deleted=()):
        self.links, self.existing, self.deleted = links, existing, set(deleted)
        self.calls, self.rows = [], []
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def execute(self, sql, params):
        self.calls.append((sql, params))
        if sql.startswith("SELECT l.gid"):
            self.rows = self.links
        else:
            table = sql.split("FROM ")[1].split()[0]
            self.rows = [{"gid": value} for value in params if value in self.existing.get(table, set()) and not ("deleted_at IS NULL" in sql and value in self.deleted)]
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class _SummaryConnection:
    def __init__(self, cursor): self.value = cursor
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def cursor(self): return self.value


def test_link_summary_batches_by_fixed_target_and_preserves_duplicate_overwrite(monkeypatch):
    from plugins.craft.craft_backend.capabilities import bop_entry_legacy_read as module
    def link(gid, entity, kind='tool', entry='entry-1', snapshot=None):
        return {'gid': gid, 'entity_gid': entity, 'link_type': kind, 'entry_gid': entry, 'is_primary': 1, 'snapshot_data': snapshot}
    links = [link('l1','exists'), link('l2','missing'), link('l3','deleted','fixture'), link('l4','opaque','physical'), link('l5','exists','tool','last-entry',{'retained':True}), link('l6','unknown','unknown')]
    cur = _SummaryCursor(links, {'tools': {'exists'}, 'fixtures': {'deleted'}}, {'deleted'})
    monkeypatch.setattr(module, 'get_craft_conn', lambda: _SummaryConnection(cur))
    monkeypatch.setattr(module, '_LINK_TARGET_TABLES', {'tool': ('tools','gid',None), 'fixture': ('fixtures','gid','deleted_at'), 'physical': None})
    result = module.read_bop_entry_legacy({'operation':'link_summary','version_gid':'v1'}, None).data['data']
    assert result['exists']['entry_gid'] == 'last-entry' and result['exists']['link_gid'] == 'l5'
    assert result['exists']['snapshot_data'] == {'retained':True}
    assert result['exists']['is_valid'] is True and result['missing']['is_valid'] is False
    assert result['deleted']['is_valid'] is False and result['opaque']['is_valid'] is True and result['unknown']['is_valid'] is True
    targets = [call for call in cur.calls if not call[0].startswith('SELECT l.gid')]
    assert len(targets) == 2
    assert any('deleted_at IS NULL' in sql for sql,_ in targets)
    assert all(' IN (' in sql for sql,_ in targets)


def test_link_summary_target_queries_are_bounded_for_large_link_sets(monkeypatch):
    from plugins.craft.craft_backend.capabilities import bop_entry_legacy_read as module
    links = [{'gid': str(i), 'entity_gid': str(i), 'link_type':'tool', 'entry_gid':'entry', 'is_primary':0, 'snapshot_data':None} for i in range(700)]
    cur = _SummaryCursor(links, {'tools': {str(i) for i in range(700)}})
    monkeypatch.setattr(module, 'get_craft_conn', lambda: _SummaryConnection(cur))
    monkeypatch.setattr(module, '_LINK_TARGET_TABLES', {'tool': ('tools','gid',None)})
    result = module.read_bop_entry_legacy({'operation':'link_summary','version_gid':'v1'}, None).data['data']
    assert len(result) == 700 and all(row['is_valid'] for row in result.values())
    targets = [call for call in cur.calls if not call[0].startswith('SELECT l.gid')]
    assert len(targets) == 3 and max(len(params) for _,params in targets) <= 256

def test_pbom_search_optional_project_filter_preserves_unscoped_contract(monkeypatch):
    from plugins.craft.craft_backend.capabilities import bop_entry_legacy_read as module
    cur = _SummaryCursor([], {})
    monkeypatch.setattr(module, 'get_craft_conn', lambda: _SummaryConnection(cur))
    module.read_bop_entry_legacy({'operation':'pbom_search','project_gid':'project-demo'}, None)
    sql, params = cur.calls[-1]
    assert 'pv.project_gid=%s' in sql and params[-3:-1] == ('project-demo','project-demo')
    module.read_bop_entry_legacy({'operation':'pbom_search'}, None)
    assert cur.calls[-1][1][-3:-1] == (None,None)
