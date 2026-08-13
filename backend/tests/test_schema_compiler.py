import json
from pathlib import Path

import pytest

from backend.capability_v2.schema_compiler import SchemaCompileError, compile_expected_schema


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
