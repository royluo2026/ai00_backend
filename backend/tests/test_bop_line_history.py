import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import importlib

_history = importlib.import_module("plugins.craft.craft_backend.routers._bop._history")
lifecycle = importlib.import_module("plugins.craft.craft_backend.routers._bop.lifecycle")


def test_build_entry_update_steps_keeps_scalar_update_after_image_steps():
    before = {
        "title": "工序A",
        "vpps": "VPPS-001",
        "process_flow_pic": [{"url": "https://img.example/existing.png"}],
    }
    patch = {
        "title": "工序A-已修改",
        "process_flow_pic": [
            {"url": "https://img.example/existing.png"},
            {"url": "https://img.example/new-1.png"},
        ],
    }

    steps = _history.build_entry_update_steps(before, patch)

    assert [step["op_type"] for step in steps] == [
        "update_entry_image_add",
        "update_entry",
    ]
    assert steps[1]["old_state"] == {"title": "工序A"}
    assert steps[1]["new_state"] == {"title": "工序A-已修改"}


class _FakeCursor:
    def __init__(self):
        self.executed = []
        self.fetchone_results = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None


class _LifecycleCursor:
    def __init__(self, fetchone_results=None, fetchall_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []


class _LifecycleConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


class _LifecycleGetConn:
    def __init__(self, conn):
        self.conn = conn

    def __call__(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _LogCursor:
    def __init__(self, fetchone_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = []
        self.executed = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        return []


class _LogConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


class _LogGetConn:
    def __init__(self, conn):
        self.conn = conn

    def __call__(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False






def test_build_create_entry_snapshot_returns_entry_link_owned_shapes():
    snapshot = _history.build_create_entry_snapshot(
        {"gid": "entry-1"},
        {"gid": "link-1"},
        {"table": "workmanship_bop_bop_process", "gid": "entity-1"},
    )
    assert set(snapshot.keys()) == {"entries", "links", "owned_entities"}
    assert snapshot["entries"][0]["gid"] == "entry-1"
    assert snapshot["links"][0]["gid"] == "link-1"
    assert snapshot["owned_entities"][0]["gid"] == "entity-1"


def test_build_delete_entry_snapshot_returns_entry_link_owned_shapes():
    snapshot = _history.build_delete_entry_snapshot(
        {"gid": "entry-1"},
        [{"gid": "link-1"}],
        [{"table": "workmanship_bop_bop_process", "gid": "entity-1"}],
    )
    assert set(snapshot.keys()) == {"entries", "links", "owned_entities"}
    assert snapshot["entries"][0]["gid"] == "entry-1"
    assert snapshot["links"][0]["gid"] == "link-1"
    assert snapshot["owned_entities"][0]["gid"] == "entity-1"


def test_redo_guard_detects_changed_entry_timestamp():
    cur = _FakeCursor()
    cur.fetchone_results = [{"updated_at": "2026-07-15T10:00:00"}]
    guard = {"entries": [{"gid": "entry-1", "updated_at": "2026-07-15T09:00:00"}]}

    assert _history.validate_redo_guard(cur, guard) is False


    cur = _FakeCursor()
    event = {
        "entity_gid": "entry-1",
        "op_type": "update_entry",
        "old_state": {
            "title": "旧标题",
            "process_flow_pic": [{"url": "https://img.example/existing.png", "object_key": "", "storage": ""}],
        },
        "new_state": {
            "title": "新标题",
        },
    }

    _history.apply_history_event(cur, event, direction="undo")

    sql, params = cur.executed[0]
    assert "UPDATE workmanship_bop_bop_entries SET" in sql
    assert "title=%s" in sql
    assert "process_flow_pic=%s" in sql
    assert params[-1] == "entry-1"


def test_apply_history_event_undo_create_entry_soft_deletes_snapshot():
    cur = _FakeCursor()
    event = {
        "entity_gid": "entry-1",
        "op_type": "create_entry",
        "new_state": {
            "entries": [{"gid": "entry-1"}],
            "links": [{"gid": "link-1"}],
            "owned_entities": [{"table": "workmanship_bop_bop_process", "gid": "entity-1"}],
        },
        "old_state": None,
    }

    _history.apply_history_event(cur, event, direction="undo")

    sqls = [sql for sql, _ in cur.executed]
    assert any("UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE" in sql for sql in sqls)
    assert len(sqls) >= 3
    assert any("UPDATE workmanship_bop_bop_process SET deleted_at=NOW()" in sql for sql in sqls)


def test_apply_history_event_undo_delete_entry_restores_snapshot():
    cur = _FakeCursor()
    event = {
        "entity_gid": "entry-1",
        "op_type": "delete_entry",
        "old_state": {
            "entries": [{"gid": "entry-1", "title": "工序A", "parent_gid": "parent-1", "node_type": "process", "vpps": "VPPS-001"}],
            "links": [{"gid": "link-1", "entry_gid": "entry-1", "version_gid": "ver-1", "link_type": "bop_process", "entity_gid": "entity-1", "is_primary": True}],
            "owned_entities": [{"table": "workmanship_bop_bop_process", "gid": "entity-1", "title": "工序A"}],
        },
        "new_state": None,
    }

    _history.apply_history_event(cur, event, direction="undo")

    sqls = [sql for sql, _ in cur.executed]
    assert any("UPDATE workmanship_bop_bop_entries SET" in sql and "is_deleted=FALSE" in sql for sql in sqls)
    assert any("INSERT INTO workmanship_bop_bop_entry_links" in sql for sql in sqls)
    assert any("UPDATE workmanship_bop_bop_process SET" in sql and "deleted_at=NULL" in sql for sql in sqls)


def test_undo_line_history_replays_latest_active_batch(monkeypatch):
    cursor = _LifecycleCursor(
        fetchone_results=[{"batch_id": "batch-1"}],
        fetchall_results=[[
            {
                "gid": "log-1",
                "batch_id": "batch-1",
                "op_type": "update_entry",
                "entity_gid": "entry-1",
                "old_state": {"title": "旧标题"},
                "new_state": {"title": "新标题"},
                "op_seq": 1,
            }
        ]],
    )
    monkeypatch.setattr(lifecycle, "get_conn", _LifecycleGetConn(_LifecycleConn(cursor)))
    calls = []
    monkeypatch.setattr(lifecycle, "_history", _history)
    monkeypatch.setattr(_history, "ensure_history_schema", lambda cur: None)
    monkeypatch.setattr(_history, "apply_history_event", lambda cur, event, direction: calls.append((event["op_type"], direction)))
    monkeypatch.setattr(_history, "mark_batch_status", lambda cur, version_gid, line_gid, batch_id, status, user_gid=None: calls.append((batch_id, status)))

    result = lifecycle.undo_line_history("ver-1", "line-1", _u={"gid": "user-1"})

    assert result == {"batch_id": "batch-1", "status": "undone"}
    assert calls[0] == ("update_entry", "undo")
    assert calls[1] == ("batch-1", "undone")


def test_redo_line_history_replays_latest_undone_batch(monkeypatch):
    cursor = _LifecycleCursor(
        fetchone_results=[{"batch_id": "batch-2"}],
        fetchall_results=[[
            {
                "gid": "log-2",
                "batch_id": "batch-2",
                "op_type": "update_entry",
                "entity_gid": "entry-1",
                "old_state": {"title": "旧标题"},
                "new_state": {"title": "新标题"},
                "op_seq": 1,
            }
        ]],
    )
    monkeypatch.setattr(lifecycle, "get_conn", _LifecycleGetConn(_LifecycleConn(cursor)))
    calls = []
    monkeypatch.setattr(lifecycle, "_history", _history)
    monkeypatch.setattr(_history, "ensure_history_schema", lambda cur: None)
    monkeypatch.setattr(_history, "apply_history_event", lambda cur, event, direction: calls.append((event["op_type"], direction)))
    monkeypatch.setattr(_history, "mark_batch_status", lambda cur, version_gid, line_gid, batch_id, status, user_gid=None: calls.append((batch_id, status)))

    result = lifecycle.redo_line_history("ver-1", "line-1", _u={"gid": "user-1"})

    assert result == {"batch_id": "batch-2", "status": "active"}
    assert calls[0] == ("update_entry", "redo")
    assert calls[1] == ("batch-2", "active")
