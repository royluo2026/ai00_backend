from pathlib import Path

import pytest

from backend.capability_v2.schema_diff import diff_schema
from backend.capability_v2.schema_model import ColumnSpec, ExpectedSchema, IndexSpec, TableSpec
from backend.capability_v2.schema_snapshot import SnapshotError, load_schema_snapshot
from backend.capability_v2.schema_snapshot import SchemaSnapshot, SnapshotColumn, SnapshotTable


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


def test_mysql_display_width_boolean_and_timestamp_renderings_are_equivalent():
    expected = ExpectedSchema((TableSpec(
        "workmanship_device_assets", "device", "device", False,
        columns=(
            ColumnSpec("count", "INT", False),
            ColumnSpec("enabled", "BOOLEAN", False, "1"),
            ColumnSpec("updated_at", "DATETIME(6)", False, "CURRENT_TIMESTAMP(6)"),
            ColumnSpec("optional", "VARCHAR(32)", True, "NULL"),
            ColumnSpec("disabled", "BOOLEAN", False, "FALSE"),
            ColumnSpec("success_rate", "DECIMAL(5,4)", False, "0"),
        ),
    ),), database_name="ai00_test")
    actual = SchemaSnapshot("ai00_test", (SnapshotTable(
        "workmanship_device_assets", "InnoDB", "utf8mb4_general_ci", "BASE TABLE",
        columns=(
            SnapshotColumn("count", 1, None, False, "INT", "INT(11)", "", "", None, None, ""),
            SnapshotColumn("enabled", 2, "1", False, "TINYINT", "TINYINT(1)", "", "", None, None, ""),
            SnapshotColumn("updated_at", 3, "CURRENT_TIMESTAMP", False, "DATETIME", "DATETIME(6)", "", "DEFAULT_GENERATED", None, None, ""),
            SnapshotColumn("optional", 4, None, True, "VARCHAR", "VARCHAR(32)", "", "", "utf8mb4", "utf8mb4_general_ci", ""),
            SnapshotColumn("disabled", 5, "0", False, "TINYINT", "TINYINT(1)", "", "", None, None, ""),
            SnapshotColumn("success_rate", 6, "0.0000", False, "DECIMAL", "DECIMAL(5,4)", "", "", None, None, ""),
        ), indexes=(),
    ),))
    diff = diff_schema(expected, actual)
    assert diff.safe == ()
    assert diff.manual == ()


def test_column_order_is_not_a_schema_contract_difference():
    expected = ExpectedSchema((TableSpec(
        "workmanship_device_assets", "device", "device", False,
        columns=(
            ColumnSpec("gid", "CHAR(36)", False),
            ColumnSpec("status", "VARCHAR(32)", False),
        ),
    ),), database_name="ai00_test")
    actual = SchemaSnapshot("ai00_test", (SnapshotTable(
        "workmanship_device_assets", "InnoDB", "utf8mb4_general_ci", "BASE TABLE",
        columns=(
            SnapshotColumn("status", 1, None, False, "VARCHAR", "VARCHAR(32)", "", "", "utf8mb4", "utf8mb4_general_ci", ""),
            SnapshotColumn("gid", 2, None, False, "CHAR", "CHAR(36)", "", "", "utf8mb4", "utf8mb4_general_ci", ""),
        ), indexes=(),
    ),))

    diff = diff_schema(expected, actual)

    assert diff.safe == ()
    assert diff.manual == ()


def test_enum_literal_case_is_a_schema_contract_difference():
    expected = ExpectedSchema((TableSpec(
        "workmanship_device_assets", "device", "device", False,
        columns=(ColumnSpec("status", "ENUM('in_use','maintenance')", False, "'in_use'"),),
    ),), database_name="ai00_test")
    actual = SchemaSnapshot("ai00_test", (SnapshotTable(
        "workmanship_device_assets", "InnoDB", "utf8mb4_general_ci", "BASE TABLE",
        columns=(
            SnapshotColumn("status", 1, "IN_USE", False, "ENUM", "ENUM('IN_USE','MAINTENANCE')", "", "", "utf8mb4", "utf8mb4_general_ci", ""),
        ), indexes=(),
    ),))

    diff = diff_schema(expected, actual)

    assert [item.kind for item in diff.manual] == ["type_mismatch", "default_mismatch"]


def _generated_diff(expected_expression, actual_expression, *, actual_default=None, missing=False):
    expected = ExpectedSchema((TableSpec("workmanship_device_assets", "device", "device", False,
        columns=(ColumnSpec("active_slot", "TINYINT", True, extra="STORED GENERATED", generation_expression=expected_expression),)),))
    actual = SchemaSnapshot("ai00_test", (SnapshotTable("workmanship_device_assets", "InnoDB", "utf8mb4_general_ci", "BASE TABLE",
        columns=() if missing else (SnapshotColumn("active_slot", 1, actual_default, True, "TINYINT", "TINYINT(4)", "", "STORED GENERATED", None, None, actual_expression),), indexes=()),))
    return diff_schema(expected, actual)


def test_generated_expression_equivalent_oceanbase_rendering_and_default():
    live = "case when ((`deleted_at` is NULL) and (`space_kind` = 'team')) then 1 else NULL end"
    diff = _generated_diff("CASE WHEN deleted_at IS NULL AND space_kind='team' THEN 1 ELSE NULL END", live, actual_default=live)
    assert diff.safe == ()
    assert diff.manual == ()


@pytest.mark.parametrize("actual", [
    "CASE WHEN deleted_at IS NULL AND space_kind='personal' THEN 1 ELSE NULL END",
    "CASE WHEN deleted_at IS NULL OR space_kind='team' THEN 1 ELSE NULL END",
    "CASE WHEN deleted_at IS NULL AND space_kind='team' THEN 2 ELSE NULL END",
    "",
])
def test_generated_expression_changes_remain_manual(actual):
    diff = _generated_diff("CASE WHEN deleted_at IS NULL AND space_kind='team' THEN 1 ELSE NULL END", actual)
    assert [item.kind for item in diff.manual] == ["generated_expression_mismatch"]


def test_generated_column_with_unrelated_default_is_not_ignored():
    diff = _generated_diff("NULLIF(gid,'null')", "NULLIF(`gid`,'null')", actual_default="unrelated")
    assert [item.kind for item in diff.manual] == ["default_mismatch"]


def test_missing_generated_column_requires_manual_migration():
    diff = _generated_diff("NULLIF(gid,'null')", "", missing=True)
    assert diff.safe == ()
    assert [item.kind for item in diff.manual] == ["missing_generated_column"]


def test_generated_comparison_precedence_cannot_hide_expression_drift():
    import sqlite3
    with sqlite3.connect(":memory:") as connection:
        assert connection.execute("SELECT a = b IS NULL, a = (b IS NULL) FROM (SELECT 0 AS a, NULL AS b)").fetchone() == (1, 0)
    diff = _generated_diff("a = b IS NULL", "a = (b IS NULL)")
    assert [item.kind for item in diff.manual] == ["generated_expression_mismatch"]
