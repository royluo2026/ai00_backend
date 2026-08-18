from __future__ import annotations

from dataclasses import replace

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
        if query.startswith("SELECT snapshot_gid, scan_run_gid"):
            self.row = self.connection.snapshot_rows.pop(0) if self.connection.snapshot_rows else None
            self.rows = []
        elif query.startswith("SELECT snapshot_entry_gid"):
            self.rows = self.connection.snapshot_entry_rows
            self.row = None
        elif query.startswith("SELECT implementation_node_gid"):
            self.rows = self.connection.node_rows
            self.row = None
        elif query.startswith("SELECT binding_gid"):
            self.rows = self.connection.binding_rows
            self.row = None
        elif query.startswith("SELECT relation_gid"):
            self.rows = self.connection.relation_rows
            self.row = None
        elif query.startswith("SELECT capability_gid"):
            self.row = self.connection.logical_rows.pop(0) if self.connection.logical_rows else None
            self.rows = []
        elif query.startswith("SELECT capability_version_gid"):
            self.row = self.connection.major_rows.pop(0) if self.connection.major_rows else None
            self.rows = []
        else:
            self.row = None
            self.rows = []
        if query.startswith("INSERT INTO workmanship_base_capability_entries") and self.connection.duplicate_logical_once:
            self.connection.duplicate_logical_once = False
            raise _DuplicateKeyError()
        if query.startswith("INSERT INTO workmanship_base_capability_snapshots") and self.connection.duplicate_snapshot_once:
            self.connection.duplicate_snapshot_once = False
            raise _DuplicateKeyError()

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _Connection:
    def __init__(self, logical_rows=(), major_rows=(), snapshot_rows=(), snapshot_entry_rows=(), node_rows=(), binding_rows=(), relation_rows=(), duplicate_logical_once=False, duplicate_snapshot_once=False):
        self.logical_rows = list(logical_rows)
        self.major_rows = list(major_rows)
        self.snapshot_rows = list(snapshot_rows)
        self.snapshot_entry_rows = list(snapshot_entry_rows)
        self.node_rows = list(node_rows)
        self.binding_rows = list(binding_rows)
        self.relation_rows = list(relation_rows)
        self.duplicate_logical_once = duplicate_logical_once
        self.duplicate_snapshot_once = duplicate_snapshot_once
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
    assert record.entries[0].capability_gid > 0
    assert all(isinstance(parameters, tuple) for _, parameters in connection.calls)
    statements = "\n".join(query for query, _ in connection.calls)
    assert "INSERT INTO workmanship_base_capability_snapshots" in statements
    assert "INSERT INTO workmanship_base_capability_snapshot_entries" in statements
    assert "INSERT INTO workmanship_base_capability_implementation_nodes" in statements
    assert "INSERT INTO workmanship_base_capability_bindings" in statements
    assert "INSERT INTO workmanship_base_capability_implementation_relations" in statements
    assert "UPDATE workmanship_base_capability_versions" in statements


def test_sql_repeat_import_reuses_existing_immutable_snapshot_without_inserts():
    document = snapshot("craft.bop.version.list", 1)
    connection = _Connection(
        snapshot_rows=({"snapshot_gid": 700, "scan_run_gid": 701, "snapshot_hash": document.snapshot_hash,
                        "code_revision": document.code_revision, "catalog_release_id": document.product_release_id,
                        "descriptor_count": 1},),
        snapshot_entry_rows=({"snapshot_entry_gid": 702, "capability_gid": 703, "capability_version_gid": 704,
                              "capability_id": "craft.bop.version.list", "major_version": 1, "owner_domain": "craft",
                              "semantic_class": "query", "business_effect": "Lists governed versions.",
                              "lifecycle_status": "active", "descriptor_hash": "sha256:" + "a" * 64},),
        node_rows=({"implementation_node_gid": 705, "canonical_key": "provider:craft.bop"},),
        binding_rows=({"binding_gid": 706},), relation_rows=({"relation_gid": 707},),
    )

    record = project_snapshot(SqlGovernanceStore(connection), document)

    assert record.snapshot_gid == 700
    assert record.entries[0].capability_gid == 703
    assert connection.commits == 0
    assert not any(query.startswith("INSERT INTO") for query, _ in connection.calls)


def test_sql_existing_snapshot_rejects_changed_document_with_reused_hash():
    document = snapshot("craft.bop.version.list", 1)
    changed = replace(document, extension_release_id="governance-2.0")
    connection = _Connection(
        snapshot_rows=({"snapshot_gid": 700, "scan_run_gid": 701, "snapshot_hash": document.snapshot_hash,
                        "code_revision": document.code_revision, "catalog_release_id": document.product_release_id,
                        "descriptor_count": 1},),
        snapshot_entry_rows=({"snapshot_entry_gid": 702, "capability_gid": 703, "capability_version_gid": 704,
                              "capability_id": "craft.bop.version.list", "major_version": 1, "owner_domain": "craft",
                              "semantic_class": "query", "business_effect": "Lists governed versions.",
                              "lifecycle_status": "active", "descriptor_hash": "sha256:" + "a" * 64},),
    )

    with pytest.raises(ImmutableRecordError, match="snapshot_hash_mismatch"):
        project_snapshot(SqlGovernanceStore(connection), changed)


def test_sql_snapshot_duplicate_race_rolls_back_provisional_scan_and_reuses_winner():
    document = snapshot("craft.bop.version.list", 1)
    connection = _Connection(
        snapshot_rows=(None, {"snapshot_gid": 700, "scan_run_gid": 701, "snapshot_hash": document.snapshot_hash,
                              "code_revision": document.code_revision, "catalog_release_id": document.product_release_id,
                              "descriptor_count": 1}),
        snapshot_entry_rows=({"snapshot_entry_gid": 702, "capability_gid": 703, "capability_version_gid": 704,
                              "capability_id": "craft.bop.version.list", "major_version": 1, "owner_domain": "craft",
                              "semantic_class": "query", "business_effect": "Lists governed versions.",
                              "lifecycle_status": "active", "descriptor_hash": "sha256:" + "a" * 64},),
        node_rows=({"implementation_node_gid": 705, "canonical_key": "provider:craft.bop"},),
        binding_rows=({"binding_gid": 706},), relation_rows=({"relation_gid": 707},),
        duplicate_snapshot_once=True,
    )

    record = project_snapshot(SqlGovernanceStore(connection, next_ids=iter(range(100, 200)).__next__), document)

    assert record.snapshot_gid == 700
    assert connection.rollbacks == 1
    assert connection.commits == 0


def test_sql_new_major_records_first_seen_snapshot_gid_and_only_updates_allowed_entry_fields():
    connection = _Connection()
    record = project_snapshot(SqlGovernanceStore(connection, next_ids=iter(range(100, 200)).__next__), snapshot("craft.bop.version.list", 1))

    version_insert = next(parameters for query, parameters in connection.calls if query.startswith("INSERT INTO workmanship_base_capability_versions"))
    entry_update = next(query for query, _ in connection.calls if query.startswith("UPDATE workmanship_base_capability_entries"))
    assert version_insert[6] == record.snapshot_gid
    assert "current_major_version" not in entry_update
    assert "current_lifecycle_status" in entry_update
    assert "last_seen_at" in entry_update
    assert "row_version" in entry_update


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


def test_sql_duplicate_key_recovery_rejects_tuple_row_with_other_owner():
    connection = _Connection(
        logical_rows=(None, (999, "craft.bop.version.list", "other")),
        duplicate_logical_once=True,
    )

    with pytest.raises(ImmutableRecordError, match="logical owner mismatch"):
        project_snapshot(SqlGovernanceStore(connection, next_ids=iter(range(100, 200)).__next__), snapshot("craft.bop.version.list", 1))

    assert connection.commits == 0
    assert connection.rollbacks == 1
