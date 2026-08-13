import re

import pytest

from backend.capability_v2.schema_diff import SchemaDiff, SchemaDifference
from backend.capability_v2.schema_model import ColumnSpec, ExpectedSchema, IndexSpec, TableSpec
from backend.capability_v2.schema_sql import SchemaPlanError, build_execution_package


def _expected():
    assets = TableSpec(
        "workmanship_device_assets", "device", "device", False,
        columns=(ColumnSpec("gid", "CHAR(36)", False), ColumnSpec("status", "VARCHAR(32)", True)),
        indexes=(IndexSpec("PRIMARY", ("gid",), True, True), IndexSpec("ix_status", ("status",))),
        sources=("backend/db/migrations/domains/device/0001_device.sql",),
    )
    new = TableSpec(
        "workmanship_device_new", "device", "device", False,
        columns=(ColumnSpec("gid", "CHAR(36)", False),),
        indexes=(IndexSpec("PRIMARY", ("gid",), True, True),),
    )
    return ExpectedSchema((assets, new), database_name="ai00_test")


def _safe_diff(expected):
    assets, new = expected.tables
    return SchemaDiff("ai00_test", expected.schema_sha256, (
        SchemaDifference("missing_table", new.name, expected_object=new),
        SchemaDifference("missing_nullable_column", assets.name, "status", expected_object=assets.columns[1]),
        SchemaDifference("missing_index", assets.name, "ix_status", expected_object=assets.indexes[1]),
    ), ())


def test_execution_package_contains_only_allowlisted_files(tmp_path):
    expected = _expected()
    build_execution_package(expected=expected, diff=_safe_diff(expected), output=tmp_path)
    assert {path.name for path in tmp_path.iterdir()} == {
        "00-export-schema.sql", "01-preflight.sql", "10-create-missing-tables.sql",
        "20-add-safe-columns.sql", "30-add-missing-indexes.sql",
        "90-verify-schema.sql", "expected-schema.json", "schema-diff.json",
        "execution-checklist.md", "SHA256SUMS",
    }


def test_generated_sql_is_non_destructive_and_targets_ai00_test(tmp_path):
    expected = _expected()
    build_execution_package(expected=expected, diff=_safe_diff(expected), output=tmp_path)
    sql = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.sql"))
    assert "`ai00_test`" in sql
    assert not re.search(r"\b(DROP|TRUNCATE|DELETE|RENAME)\b", sql, re.I)
    assert "ADD COLUMN" in sql and "ADD INDEX" in sql
    assert "ENGINE=InnoDB" not in sql


def test_preflight_does_not_use_oceanbase_reserved_keyword_as_alias(tmp_path):
    expected = _expected()
    build_execution_package(expected=expected, diff=_safe_diff(expected), output=tmp_path)
    preflight = (tmp_path / "01-preflight.sql").read_text(encoding="utf-8")
    assert "CURRENT_USER() AS connected_principal" in preflight
    assert "CURRENT_USER() AS current_user" not in preflight


def test_preflight_accepts_database_scoped_ddl_privileges(tmp_path):
    expected = _expected()
    build_execution_package(expected=expected, diff=_safe_diff(expected), output=tmp_path)
    preflight = (tmp_path / "01-preflight.sql").read_text(encoding="utf-8")
    assert "information_schema.USER_PRIVILEGES" in preflight
    assert "information_schema.SCHEMA_PRIVILEGES" in preflight
    assert "TABLE_SCHEMA = 'ai00_test'" in preflight


def test_generated_sql_unwraps_parenthesized_scalar_defaults(tmp_path):
    expected = ExpectedSchema((TableSpec(
        "workmanship_factory_assets", "factory", "factory", False,
        columns=(
            ColumnSpec("gid", "CHAR(36)", False),
            ColumnSpec("status", "VARCHAR(255)", False, "('in_use')"),
            ColumnSpec("version", "BIGINT", False, "(1)"),
            ColumnSpec("snapshot_date", "DATE", False, "(CURRENT_DATE)"),
        ),
        indexes=(IndexSpec("PRIMARY", ("gid",), True, True),),
    ),), database_name="ai00_test")
    diff = SchemaDiff("ai00_test", expected.schema_sha256, (
        SchemaDifference("missing_table", "workmanship_factory_assets", expected_object=expected.tables[0]),
    ), ())
    build_execution_package(expected=expected, diff=diff, output=tmp_path)
    ddl = (tmp_path / "10-create-missing-tables.sql").read_text(encoding="utf-8")
    assert "DEFAULT 'in_use'" in ddl
    assert "DEFAULT 1" in ddl
    assert "DEFAULT CURRENT_DATE" in ddl
    assert "DEFAULT ('in_use')" not in ddl
    assert "DEFAULT (1)" not in ddl
    assert "DEFAULT (CURRENT_DATE)" not in ddl


def test_manual_diff_blocks_ddl_generation(tmp_path):
    expected = _expected()
    diff = SchemaDiff("ai00_test", expected.schema_sha256, (), (
        SchemaDifference("type_mismatch", "workmanship_device_assets", "gid"),
    ))
    with pytest.raises(SchemaPlanError, match="manual_review_required"):
        build_execution_package(expected=expected, diff=diff, output=tmp_path)
    assert not (tmp_path / "10-create-missing-tables.sql").exists()
