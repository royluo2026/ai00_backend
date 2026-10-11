import ast
from pathlib import Path

import pytest

from backend.db import table_prefix
from plugins.craft.craft_backend.capabilities import bop_lifecycle_step_rollback as rollback
from plugins.craft.craft_backend.capabilities.bop_lifecycle_step_rollback import (
    _soft_delete_links,
    apply_bop_lifecycle_step_rollback,
)


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_step_rollback_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.step.rollback.apply"') == 1
    assert "def _legacy_undo_lifecycle_step" in source


def test_legacy_direct_rollback_cannot_use_hard_delete_fallback() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    legacy = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_legacy_undo_lifecycle_step")
    body = ast.get_source_segment(source, legacy)
    assert "information_schema" not in body
    assert "DELETE FROM workmanship_bop_bop_entry_links" not in body
    assert "ref_gid" not in body
    assert "UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE" in body


def test_step_rollback_validates_step_before_io() -> None:
    with pytest.raises(ValueError, match="step_key must be one of"):
        apply_bop_lifecycle_step_rollback({"version_gid": "v1", "step_key": "unknown"}, object())


def test_step_rollback_validates_version_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_lifecycle_step_rollback({"step_key": "lines_added"}, object())


def test_step_rollback_never_falls_back_to_hard_deleting_links() -> None:
    class Cursor:
        rowcount = 3

        def __init__(self) -> None:
            self.calls = []

        def execute(self, sql, params=()):
            self.calls.append((sql, params))
            if "information_schema" in sql or "DELETE FROM" in sql:
                raise AssertionError("rollback must not probe another schema or hard-delete links")

    cursor = Cursor()
    assert _soft_delete_links(cursor, "entry_gid IN (%s)", ("e1",)) == 3
    assert cursor.calls == [(
        "UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE WHERE entry_gid IN (%s) AND is_deleted=FALSE",
        ("e1",),
    )]


def test_step_rollback_missing_soft_delete_column_fails_without_hard_delete() -> None:
    class Cursor:
        def execute(self, sql, params=()):
            if sql.startswith("UPDATE workmanship_bop_bop_entry_links SET is_deleted"):
                raise RuntimeError("column missing")
            raise AssertionError("unexpected fallback or metadata query")

    with pytest.raises(RuntimeError, match="column missing"):
        _soft_delete_links(Cursor(), "version_gid=%s", ("v1",))


def test_pbom_step_rollback_uses_declared_link_identity_and_soft_delete(monkeypatch) -> None:
    class Connection:
        rowcount = 2

        def __init__(self) -> None:
            self.calls = []
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return self

        def execute(self, sql, params=()):
            if "DELETE FROM" in sql or "information_schema" in sql or "ref_gid" in sql:
                raise AssertionError("rollback used an unsafe or undeclared link column")
            self.calls.append((sql, params))

        def fetchone(self):
            return {"lifecycle_state": "{}"}

        def commit(self):
            self.committed = True

    connection = Connection()
    monkeypatch.setattr(rollback, "get_craft_conn", lambda: connection)
    result = apply_bop_lifecycle_step_rollback({
        "version_gid": "v1", "step_key": "vpps_imported", "pbom_version_gid": "pbom-1",
    }, object())
    assert result["data"]["deleted_links"] == 2
    assert connection.committed
    assert "entity_gid IN (SELECT gid FROM workmanship_bop_pbom WHERE snapshot_gid=%s)" in connection.calls[1][0]
    assert connection.calls[1][1] == ("v1", "pbom-1")
    for prefix in ("test_", "pp_"):
        monkeypatch.setattr(table_prefix, "_PREFIX", prefix)
        rewritten = table_prefix.rewrite_sql(connection.calls[1][0])
        assert f"UPDATE {prefix}workmanship_bop_bop_entry_links" in rewritten
        assert f"FROM {prefix}workmanship_bop_pbom" in rewritten
        assert "ref_gid" not in rewritten
