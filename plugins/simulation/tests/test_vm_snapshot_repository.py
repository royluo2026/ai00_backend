from __future__ import annotations

import pytest

from plugins.simulation.simulation_backend.data.vm_snapshot_repository import (
    VmRepositoryError,
    VmSnapshotRepository,
)
from plugins.simulation.simulation_backend.domain.vm_identity import (
    IdentityMatch,
    SnapshotDiff,
    VmObservation,
)


class _Cursor:
    def __init__(self, rows=(), insert_rowcounts=()):
        self.rows = iter(rows)
        self.insert_rowcounts = iter(insert_rowcounts)
        self.rowcount = 0
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        if sql.lstrip().upper().startswith("SELECT"):
            self._current = next(self.rows, None)
            self.rowcount = 1 if self._current else 0
        else:
            self.rowcount = next(self.insert_rowcounts, 1)

    def fetchone(self):
        return self._current


class _Connection:
    def __init__(self, cursor):
        self.value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.value


def test_create_document_is_owner_scoped_and_returns_decimal_string_gid():
    cursor = _Cursor(insert_rowcounts=(1,))
    repository = VmSnapshotRepository(lambda: _Connection(cursor), gid_factory=lambda: 9001)
    gid = repository.create_document(
        workspace_gid="10",
        tenant_gid="20",
        owner_gid="30",
        source_kind="teamcenter",
        source_identity_hash="a" * 64,
    )
    assert gid == "9001"
    sql, params = cursor.calls[0]
    assert "SELECT %s,%s,%s" in sql
    assert "tenant_gid=%s AND owner_gid=%s" in sql
    assert params[-2:] == ("20", "30")


def test_create_document_rejects_invisible_workspace():
    repository = VmSnapshotRepository(
        lambda: _Connection(_Cursor(insert_rowcounts=(0,))), gid_factory=lambda: 9001
    )
    with pytest.raises(VmRepositoryError, match="workspace_not_found"):
        repository.create_document(
            workspace_gid="10",
            tenant_gid="20",
            owner_gid="30",
            source_kind="teamcenter",
            source_identity_hash="a" * 64,
        )


def test_advance_head_uses_expected_row_version_cas():
    cursor = _Cursor(rows=({"row_version": 4},), insert_rowcounts=(1,))
    repository = VmSnapshotRepository(lambda: _Connection(cursor))
    repository.advance_head(
        document_gid="10",
        snapshot_gid="11",
        tenant_gid="20",
        owner_gid="30",
        expected_row_version=4,
    )
    update_sql, update_params = cursor.calls[-1]
    assert "row_version=row_version+1" in update_sql
    assert "row_version=%s" in update_sql
    assert update_params[-1] == 4


def test_soft_remove_is_document_and_owner_scoped():
    cursor = _Cursor(insert_rowcounts=(1,))
    repository = VmSnapshotRepository(lambda: _Connection(cursor))
    repository.soft_remove_occurrences(
        document_gid="10", occurrence_gids=("41", "42"), tenant_gid="20", owner_gid="30"
    )
    sql, params = cursor.calls[0]
    assert "removed_at=NOW(6)" in sql
    assert "document_gid=%s AND tenant_gid=%s AND owner_gid=%s" in sql
    assert params == ("10", "20", "30", "41", "42")


def test_persist_snapshot_writes_artifact_occurrence_observation_pose_and_head_atomically():
    cursor = _Cursor(rows=({"row_version": None},), insert_rowcounts=(1, 1, 1, 1, 1))
    repository = VmSnapshotRepository(
        lambda: _Connection(cursor), gid_factory=iter((9001, 9002)).__next__
    )
    observation = VmObservation(
        occurrence_gid=None,
        source_instance_id="inst-1",
        session_gid="40",
        kind="part",
        model_number="W01-89184128",
        bom_line="W01-89184128/00;1",
        revision="00",
        catia_occurrence_name="bolt-left",
        normalized_transform=("1", "0", "0", "1"),
    )
    result = repository.persist_snapshot(
        document_gid="10",
        session_gid="40",
        tenant_gid="20",
        owner_gid="30",
        sequence=1,
        artifact_gid="50",
        artifact_sha256="a" * 64,
        artifact_byte_size=123,
        snapshot_hash="b" * 64,
        parser_algorithm_version="plmxml-projection.v1",
        identity_algorithm_version="vm-identity.v1",
        captured_at="2026-09-09 00:00:00.000000",
        expected_head_row_version=0,
        diff=SnapshotDiff(
            matches=(IdentityMatch(observation, "60", "added"),),
            removed_occurrence_gids=(),
        ),
    )
    assert result == {"snapshot_gid": "9001", "head_row_version": 1}
    statements = "\n".join(sql for sql, _ in cursor.calls)
    assert "INSERT INTO workmanship_sim_vm_snapshots" in statements
    assert "INSERT INTO workmanship_sim_vm_occurrences" in statements
    assert "INSERT INTO workmanship_sim_vm_observations" in statements
    assert "INSERT INTO workmanship_sim_vm_poses" in statements
    assert "INSERT INTO workmanship_sim_vm_snapshot_heads" in statements


def test_load_latest_observations_preserves_identity_fields_and_head_version():
    row = {"occurrence_gid": 60, "status": "active", "kind": "part", "model_number": "P1",
           "session_gid": 40, "source_instance_id": "i1", "bom_line": "P1/00;1",
           "revision_code": "00", "catia_occurrence_name": "left", "parent_path_json": '["root"]',
           "normalized_transform_json": '["1","0"]', "raw_transform_json": '["1.0","0"]',
           "representation_locations_json": '["opaque.jt"]', "row_version": 3, "sequence": 7}
    cursor = _Cursor(rows=(row,))
    cursor.fetchall = lambda: [row]
    result = VmSnapshotRepository(lambda: _Connection(cursor)).load_latest_observations(document_gid="10", tenant_gid="20", owner_gid="30")
    assert result["head_row_version"] == 3 and result["sequence"] == 7
    assert result["observations"][0].parent_path == ("root",)
    assert result["observations"][0].representation_locations == ("opaque.jt",)
