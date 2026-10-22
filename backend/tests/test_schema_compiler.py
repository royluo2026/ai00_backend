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


def test_compiler_preserves_enum_literal_case(tmp_path):
    _repository(
        tmp_path,
        ("schema/01.sql", """
          CREATE TABLE workmanship_device_assets (
            gid CHAR(36) PRIMARY KEY,
            status ENUM('in_use','MAINTENANCE') NOT NULL DEFAULT 'in_use'
          );
        """),
    )

    status = compile_expected_schema(tmp_path).require_table(
        "workmanship_device_assets"
    ).require_column("status")

    assert status.data_type == "ENUM('in_use','MAINTENANCE')"
    assert status.default == "'in_use'"


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


def test_alter_add_constraint_is_not_a_column(tmp_path):
    _repository(tmp_path, ("schema/01.sql", """
      CREATE TABLE workmanship_device_assets (status VARCHAR(32));
      ALTER TABLE workmanship_device_assets ADD CONSTRAINT device_status CHECK (status IN ('active','retired'));
    """))
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert [column.name for column in table.columns] == ["status"]
    assert [(item.name, item.kind, item.expression) for item in table.constraints] == [
        ("device_status", "check", "status IN ('active','retired')")]


def _runtime_status_repository(tmp_path, initial, migration):
    _repository(tmp_path, ("schema/01.sql", f"""
      CREATE TABLE workmanship_device_assets (status VARCHAR(32), {initial});
    """), ("schema/02.sql", migration))
    for path in tmp_path.rglob("*.sql"):
        path.write_text(path.read_text().replace("workmanship_device_assets", "workmanship_sim_connector_runtime_plans"))
    path = tmp_path / "backend/governance/domain_table_ownership.json"
    path.write_text(path.read_text().replace("workmanship_device_assets", "workmanship_sim_connector_runtime_plans"))


OLD_STATUS = "'queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired'"
EXPANDED_STATUS = OLD_STATUS + ",'cancelled'"
STATUS_MIGRATION = (ROOT / "backend/db/migrations/domains/simulation/0027_connector_manual_recovery_status.sql").read_text()


def test_guarded_status_retirement_resolves_actual_old_constraint(tmp_path):
    _runtime_status_repository(tmp_path, f"CONSTRAINT generated_check_42 CHECK (status IN ({OLD_STATUS}))", STATUS_MIGRATION)
    table = compile_expected_schema(tmp_path).require_table("workmanship_sim_connector_runtime_plans")
    assert [column.name for column in table.columns] == ["status"]
    assert [(item.name, item.expression) for item in table.constraints] == [
        ("sim_runtime_plan_status_recovery", f"status IN ({EXPANDED_STATUS})")]


@pytest.mark.parametrize("initial,migration", [
    (f"CHECK (status IN ({OLD_STATUS}))", "-- AI00: RESUMABLE RETIRE OLD STATUS CHECK\nALTER TABLE workmanship_sim_connector_runtime_plans DROP CHECK sim_runtime_plan_status_pre_recovery;"),
    ("CHECK (status IN ('unknown'))", STATUS_MIGRATION),
    (f"CHECK (status IN ({OLD_STATUS})), CONSTRAINT duplicate_old CHECK (status IN ({OLD_STATUS}))", STATUS_MIGRATION),
    (f"CHECK (status IN ({OLD_STATUS}))", STATUS_MIGRATION.replace("'cancelled'", "'unexpected'")),
])
def test_guarded_status_retirement_rejects_unverified_replacements(tmp_path, initial, migration):
    _runtime_status_repository(tmp_path, initial, migration)
    with pytest.raises(SchemaCompileError, match="invalid_status_check_replacement"):
        compile_expected_schema(tmp_path)


@pytest.mark.parametrize("definition,name,columns", [
    ("CONSTRAINT `uq_sim_viewer_grant_generation` UNIQUE (`source_association_id`,`session_nonce`,`grant_generation`)",
     "uq_sim_viewer_grant_generation", ("source_association_id", "session_nonce", "grant_generation")),
    ("UNIQUE (source_association_id,session_nonce)", "source_association_id", ("source_association_id", "session_nonce")),
    ("UNIQUE KEY (source_association_id)", "source_association_id", ("source_association_id",)),
])
def test_compiles_unique_constraint_without_bogus_columns(tmp_path, definition, name, columns):
    _repository(tmp_path, ("schema/01.sql", f"""
      CREATE TABLE workmanship_device_assets (
        source_association_id VARCHAR(64), session_nonce CHAR(64), grant_generation BIGINT,
        {definition}
      );
    """))
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert [column.name for column in table.columns] == ["source_association_id", "session_nonce", "grant_generation"]
    assert table.require_index(name).columns == columns
    assert table.require_index(name).unique is True


def test_inline_unique_uses_mysql_column_name(tmp_path):
    _repository(tmp_path, ("schema/01.sql", """
      CREATE TABLE workmanship_device_assets (gid VARCHAR(128) PRIMARY KEY, token_hash CHAR(64) NOT NULL UNIQUE);
    """))
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert [(index.name, index.columns) for index in table.indexes] == [("PRIMARY", ("gid",)), ("token_hash", ("token_hash",))]


@pytest.mark.parametrize("action", ["ADD COLUMN token_hash CHAR(64) NOT NULL UNIQUE", "ADD KEY (gid)"])
def test_alter_preserves_inline_and_unnamed_indexes(tmp_path, action):
    _repository(tmp_path, ("schema/01.sql", f"CREATE TABLE workmanship_device_assets (gid INT PRIMARY KEY); ALTER TABLE workmanship_device_assets {action};"))
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    name = "token_hash" if "token_hash" in action else "gid"
    assert table.require_index(name).columns == (name,)


def test_mysql_unnamed_indexes_receive_collision_suffixes(tmp_path):
    _repository(tmp_path, ("schema/01.sql", "CREATE TABLE workmanship_device_assets (gid INT, UNIQUE (gid), UNIQUE (gid));"))
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert [index.name for index in table.indexes] == ["gid", "gid_2"]


@pytest.mark.parametrize("definition", ["UNIQUE BROKEN syntax", "CONSTRAINT unsupported_clause SOME unsupported", "FULLTEXT KEY unsupported (gid)"])
def test_rejects_unsupported_table_constraints_instead_of_columns(tmp_path, definition):
    _repository(tmp_path, ("schema/01.sql", f"CREATE TABLE workmanship_device_assets (gid INT, {definition});"))
    with pytest.raises(SchemaCompileError, match="unsupported_table_item"):
        compile_expected_schema(tmp_path)


def test_real_migrations_preserve_viewer_grant_unique_and_enrollment_index_names():
    schema = compile_expected_schema(ROOT)
    grants = schema.require_table("workmanship_sim_viewer_interaction_grants")
    assert "unique" not in [column.name for column in grants.columns]
    assert grants.require_index("uq_sim_viewer_grant_generation").columns == ("source_association_id", "session_nonce", "grant_generation")
    enrollments = schema.require_table("workmanship_sim_connector_enrollments")
    assert enrollments.require_index("token_hash").unique is True


def test_generated_column_preserves_nested_expression_and_storage(tmp_path):
    _repository(tmp_path, ("schema/01.sql", """
      CREATE TABLE workmanship_device_assets (
        plan_json JSON,
        cache_file_batch VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin
        GENERATED ALWAYS AS (CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(plan_json,'$.NOT NULL'))='UNIQUE' THEN NULLIF(JSON_UNQUOTE(JSON_EXTRACT(plan_json,'$.batch_id')),'null') ELSE NULL END) STORED
      );
    """))
    column = compile_expected_schema(tmp_path).require_table("workmanship_device_assets").require_column("cache_file_batch")
    assert column.nullable is True
    assert column.data_type == "VARCHAR(32)"
    assert column.extra == "STORED GENERATED"
    assert getattr(column, "generation_expression", None) == "CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(plan_json,'$.NOT NULL'))='UNIQUE' THEN NULLIF(JSON_UNQUOTE(JSON_EXTRACT(plan_json,'$.batch_id')),'null') ELSE NULL END"


def test_generated_expression_is_bound_to_schema_hash_and_round_trip():
    from dataclasses import replace
    from backend.capability_v2.schema_model import expected_schema_from_dict
    schema = compile_expected_schema(ROOT)
    assert expected_schema_from_dict(schema.to_dict()) == schema
    table = schema.require_table("workmanship_sim_cloud_cache_nodes")
    column = table.require_column("parent_node_key")
    assert getattr(column, "generation_expression", None) == "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.parent_occurrence_id')),'null')"
    changed_table = replace(table, columns=tuple(replace(c, generation_expression="NULL") if c.name == column.name else c for c in table.columns))
    assert replace(schema, tables=tuple(changed_table if t.name == table.name else t for t in schema.tables)).schema_sha256 != schema.schema_sha256


def test_column_attributes_do_not_rewrite_literal_whitespace(tmp_path):
    _repository(tmp_path, ("schema/01.sql", """
      CREATE TABLE workmanship_device_assets (
        label VARCHAR(32) DEFAULT 'a  b',
        generated_label VARCHAR(32) GENERATED ALWAYS AS (NULLIF(label,'a  b')) VIRTUAL
      );
    """))
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert table.require_column("label").default == "'a  b'"
    assert table.require_column("generated_label").generation_expression == "NULLIF(label,'a  b')"


def test_generated_literal_on_update_is_not_a_column_attribute(tmp_path):
    _repository(tmp_path, ("schema/01.sql", """
      CREATE TABLE workmanship_device_assets (
        label VARCHAR(32),
        generated_label VARCHAR(32) GENERATED ALWAYS AS (NULLIF(label,'ON UPDATE NULL')) STORED
      );
    """))
    table = compile_expected_schema(tmp_path).require_table("workmanship_device_assets")
    assert table.require_column("generated_label").extra == "STORED GENERATED"
    assert table.require_column("generated_label").generation_expression == "NULLIF(label,'ON UPDATE NULL')"
