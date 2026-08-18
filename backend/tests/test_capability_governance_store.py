from __future__ import annotations

import pytest

from backend.capability_governance_test.identity_projection import project_snapshot
from backend.capability_governance_test.models import ImmutableRecordError
from backend.capability_governance_test.store import MemoryGovernanceStore, SqlGovernanceStore
from backend.tests.test_capability_identity_projection import snapshot


def test_snapshot_is_insert_only():
    store = MemoryGovernanceStore()
    saved = store.save_snapshot(snapshot("base.project.search", 1))

    with pytest.raises(ImmutableRecordError):
        store.replace_snapshot(saved.snapshot_gid, snapshot("base.project.create", 1))


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def execute(self, query, parameters=()):
        self.connection.calls.append((query, parameters))
        assert "%s" in query or query.startswith("UPDATE")
        if query.startswith("SELECT capability_gid"):
            self.row = self.connection.logical_rows.pop(0) if self.connection.logical_rows else None
        elif query.startswith("SELECT capability_version_gid"):
            self.row = self.connection.major_rows.pop(0) if self.connection.major_rows else None
        else:
            self.row = None
        if query.startswith("INSERT INTO workmanship_base_capability_entries") and self.connection.duplicate_logical_once:
            self.connection.duplicate_logical_once = False
            raise _DuplicateKeyError()

    def fetchone(self):
        return self.row

    def close(self):
        pass


class _Connection:
    def __init__(self, logical_rows=(), major_rows=(), duplicate_logical_once=False):
        self.logical_rows = list(logical_rows)
        self.major_rows = list(major_rows)
        self.duplicate_logical_once = duplicate_logical_once
        self.calls = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _DuplicateKeyError(Exception):
    pass


def test_sql_store_uses_one_parameterized_transaction_and_persists_graph():
    connection = _Connection()
    record = project_snapshot(SqlGovernanceStore(connection, next_ids=iter(range(100, 200)).__next__), snapshot("craft.bop.version.list", 1))

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert record.entries[0].capability_gid == 100
    assert all(isinstance(parameters, tuple) for _, parameters in connection.calls)
    statements = "\n".join(query for query, _ in connection.calls)
    assert "INSERT INTO workmanship_base_capability_snapshots" in statements
    assert "INSERT INTO workmanship_base_capability_snapshot_entries" in statements
    assert "INSERT INTO workmanship_base_capability_implementation_nodes" in statements
    assert "INSERT INTO workmanship_base_capability_bindings" in statements
    assert "INSERT INTO workmanship_base_capability_implementation_relations" in statements
    assert "UPDATE workmanship_base_capability_versions" in statements


def test_sql_duplicate_key_recovery_re_reads_matching_identity():
    connection = _Connection(
        logical_rows=(None, {"capability_gid": 999, "capability_id": "craft.bop.version.list"}),
        major_rows=(None,),
        duplicate_logical_once=True,
    )
    record = project_snapshot(SqlGovernanceStore(connection, next_ids=iter(range(100, 200)).__next__), snapshot("craft.bop.version.list", 1))

    assert record.entries[0].capability_gid == 999
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_sql_store_rolls_back_if_duplicate_identity_does_not_match():
    connection = _Connection(
        logical_rows=(None, {"capability_gid": 999, "capability_id": "other.capability"}),
        duplicate_logical_once=True,
    )

    with pytest.raises(ImmutableRecordError, match="identity_conflict"):
        project_snapshot(SqlGovernanceStore(connection, next_ids=iter(range(100, 200)).__next__), snapshot("craft.bop.version.list", 1))

    assert connection.commits == 0
    assert connection.rollbacks == 1
