import json
from pathlib import Path

import pytest

from backend.capability_v2.schema_compiler import SchemaCompileError, compile_expected_schema


ROOT = Path(__file__).resolve().parents[2]


def _repository(tmp_path: Path, *sql_files: tuple[str, str]):
    manifest = {
        "schema_version": 1,
        "domains": [{
            "domain_id": "device",
            "database": {"schema_paths": [name for name, _ in sql_files]},
        }],
    }
    ownership = {
        "schema_version": 1,
        "tables": [{
            "table": "workmanship_device_assets",
            "owner": "device",
            "runtime_domain": "device",
            "legacy_name": False,
        }],
    }
    for relative, sql in sql_files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sql, encoding="utf-8")
    manifest_path = tmp_path / "backend/capability_v2/official_domains.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ownership_path = tmp_path / "backend/governance/domain_table_ownership.json"
    ownership_path.parent.mkdir(parents=True, exist_ok=True)
    ownership_path.write_text(json.dumps(ownership), encoding="utf-8")
    profile_path = tmp_path / "backend/capability_v2/database_profiles/single_database.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps({
        "database_name": "ai00_test",
        "isolation_profile": "single_database_domain_tables",
    }), encoding="utf-8")


def test_compiles_create_alter_and_indexes_deterministically(tmp_path):
    _repository(
        tmp_path,
        ("schema/01.sql", """
          CREATE TABLE IF NOT EXISTS workmanship_device_assets (
            gid CHAR(36) NOT NULL,
            asset_no VARCHAR(64) NOT NULL,
            PRIMARY KEY (gid),
            UNIQUE KEY uq_device_asset_no (asset_no)
          );
        """),
        ("schema/02.sql", """
          ALTER TABLE workmanship_device_assets
            ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active' AFTER asset_no;
          CREATE INDEX IF NOT EXISTS ix_device_status
            ON workmanship_device_assets (status);
        """),
    )

    schema = compile_expected_schema(tmp_path)
    table = schema.require_table("workmanship_device_assets")

    assert table.owner == "device"
    assert [column.name for column in table.columns] == ["gid", "asset_no", "status"]
    assert table.require_column("status").default == "'active'"
    assert table.require_index("PRIMARY").columns == ("gid",)
    assert table.require_index("uq_device_asset_no").unique is True
    assert table.require_index("ix_device_status").columns == ("status",)
    assert table.sources == ("schema/01.sql", "schema/02.sql")
    assert schema.to_dict() == compile_expected_schema(tmp_path).to_dict()


@pytest.mark.parametrize("sql, code", [
    ("DROP TABLE workmanship_device_assets;", "destructive_ddl"),
    ("CREATE SOMETHING workmanship_device_assets;", "unsupported_ddl"),
    ("CREATE TABLE other.workmanship_device_assets (gid INT);", "cross_database_reference"),
])
def test_rejects_unsafe_or_unparsed_ddl(tmp_path, sql, code):
    _repository(tmp_path, ("schema/bad.sql", sql))
    with pytest.raises(SchemaCompileError, match=code):
        compile_expected_schema(tmp_path)


def test_rejects_conflicting_column_definitions(tmp_path):
    _repository(
        tmp_path,
        ("schema/01.sql", "CREATE TABLE workmanship_device_assets (status VARCHAR(32));"),
        ("schema/02.sql", "ALTER TABLE workmanship_device_assets ADD COLUMN status INT;"),
    )
    with pytest.raises(SchemaCompileError, match="column_conflict:workmanship_device_assets.status"):
        compile_expected_schema(tmp_path)


def test_rejects_change_column_rename(tmp_path):
    _repository(
        tmp_path,
        ("schema/01.sql", "CREATE TABLE workmanship_device_assets (status VARCHAR(32));"),
        ("schema/02.sql", "ALTER TABLE workmanship_device_assets CHANGE status state VARCHAR(32);"),
    )
    with pytest.raises(SchemaCompileError, match="column_rename_forbidden"):
        compile_expected_schema(tmp_path)


def test_rejects_cross_domain_foreign_key(tmp_path):
    _repository(
        tmp_path,
        ("schema/01.sql", """
          CREATE TABLE workmanship_device_assets (
            gid CHAR(36), model_gid CHAR(36),
            CONSTRAINT fk_asset_model FOREIGN KEY (model_gid)
              REFERENCES workmanship_model_models(gid)
          );
          CREATE TABLE workmanship_model_models (gid CHAR(36));
        """),
    )
    ownership_path = tmp_path / "backend/governance/domain_table_ownership.json"
    ownership = json.loads(ownership_path.read_text(encoding="utf-8"))
    ownership["tables"].append({
        "table": "workmanship_model_models", "owner": "digital_model",
        "runtime_domain": "digital_model", "legacy_name": False,
    })
    ownership_path.write_text(json.dumps(ownership), encoding="utf-8")
    with pytest.raises(SchemaCompileError, match="cross_domain_foreign_key"):
        compile_expected_schema(tmp_path)


def test_primary_key_is_compiled_as_not_nullable(tmp_path):
    _repository(
        tmp_path,
        ("schema/01.sql", "CREATE TABLE workmanship_device_assets (gid CHAR(36) PRIMARY KEY);"),
    )
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert table.require_column("gid").nullable is False


def test_compiler_uses_oceanbase_normalized_json_defaults(tmp_path):
    _repository(
        tmp_path,
        ("schema/01.sql", """
          CREATE TABLE workmanship_device_assets (
            gid CHAR(36) PRIMARY KEY,
            payload JSON NOT NULL DEFAULT (JSON_OBJECT())
          );
        """),
    )
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert table.require_column("payload").default is None


def test_real_repository_uses_authoritative_runtime_ledger_contract():
    table = compile_expected_schema(ROOT).require_table("workmanship_base_schema_migrations")
    assert [(column.name, column.data_type) for column in table.columns] == [
        ("migration_id", "VARCHAR(12)"), ("domain", "VARCHAR(32)"),
        ("name", "VARCHAR(191)"), ("checksum", "CHAR(64)"),
        ("status", "VARCHAR(16)"), ("duration_ms", "BIGINT"),
        ("error", "TEXT"), ("applied_at", "DATETIME(6)"),
    ]


def test_real_repository_preserves_hash_color_defaults_and_following_columns():
    schema = compile_expected_schema(ROOT)
    sections = schema.require_table("workmanship_factory_factory_sections")
    assert sections.require_column("color").default == "('#7287fd')"
    assert sections.require_column("canvas_x").default == "0"
    assert sections.require_column("canvas_h").default == "300"
    work_lists = schema.require_table("workmanship_work_lists")
    assert work_lists.require_column("color").default == "('#5b8dee')"
    assert work_lists.require_column("storage_scope").default == "('cloud')"


def test_lifecycle_stats_date_is_required_without_unsupported_database_default():
    table = compile_expected_schema(ROOT).require_table("workmanship_bop_bop_lifecycle_stats")
    snapshot_date = table.require_column("stats_snapshot_date")
    assert snapshot_date.data_type == "DATE"
    assert snapshot_date.nullable is False
    assert snapshot_date.default is None
