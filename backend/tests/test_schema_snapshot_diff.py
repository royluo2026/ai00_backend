from pathlib import Path

import pytest

from backend.capability_v2.schema_diff import diff_schema
from backend.capability_v2.schema_model import ColumnSpec, ExpectedSchema, IndexSpec, TableSpec
from backend.capability_v2.schema_snapshot import SnapshotError, load_schema_snapshot


FIXTURE = Path(__file__).parent / "fixtures/schema_audit/live"


def _expected(*, required_default="unused"):
    assets = TableSpec(
        "workmanship_device_assets", "device", "device", False,
        columns=(
            ColumnSpec("gid", "CHAR(36)", False),
            ColumnSpec("asset_no", "VARCHAR(64)", False),
            ColumnSpec("status", "VARCHAR(32)", required_default == "unused",
                       None if required_default == "unused" else required_default),
        ),
        indexes=(
            IndexSpec("PRIMARY", ("gid",), True, True),
            IndexSpec("ix_device_status", ("status",)),
        ),
    )
    new_table = TableSpec(
        "workmanship_device_new", "device", "device", False,
        columns=(ColumnSpec("gid", "CHAR(36)", False),),
        indexes=(IndexSpec("PRIMARY", ("gid",), True, True),),
    )
    return ExpectedSchema((assets, new_table), database_name="ai00_test")


def test_snapshot_requires_exact_headers_and_unique_rows():
    snapshot = load_schema_snapshot(FIXTURE, expected_database="ai00_test")
    assert snapshot.require_table("workmanship_device_assets").require_column("gid").nullable is False
    assert snapshot.require_table("workmanship_device_assets").require_column("old_column").default == ""


def test_snapshot_rejects_duplicate_structural_rows(tmp_path):
    for source in FIXTURE.iterdir():
        target = tmp_path / source.name
        target.write_bytes(source.read_bytes())
    path = tmp_path / "ai00_test_indexes.csv"
    path.write_text(path.read_text(encoding="utf-8") + "ai00_test,workmanship_device_assets,PRIMARY,0,1,gid,NULL,BTREE,A\n", encoding="utf-8")
    with pytest.raises(SnapshotError, match="duplicate_index_row"):
        load_schema_snapshot(tmp_path, expected_database="ai00_test")


def test_snapshot_rejects_extra_header(tmp_path):
    for source in FIXTURE.iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    path = tmp_path / "ai00_test_tables.csv"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("TABLE_TYPE", "TABLE_TYPE,SECRET"), encoding="utf-8")
    with pytest.raises(SnapshotError, match="invalid_headers"):
        load_schema_snapshot(tmp_path, expected_database="ai00_test")


def test_diff_classifies_only_additive_changes_as_automatic():
    diff = diff_schema(_expected(), load_schema_snapshot(FIXTURE, expected_database="ai00_test"))
    assert [item.kind for item in diff.safe] == ["missing_table", "missing_nullable_column", "missing_index"]
    assert [item.kind for item in diff.manual] == ["type_mismatch", "unexpected_column"]


def test_not_null_column_without_deterministic_default_is_manual():
    expected = _expected(required_default=None)
    diff = diff_schema(expected, load_schema_snapshot(FIXTURE, expected_database="ai00_test"))
    assert not any(item.kind == "missing_nullable_column" for item in diff.safe)
    assert any(item.kind == "missing_required_column_without_backfill" for item in diff.manual)
