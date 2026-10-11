from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.domain_migrations import (
    DomainMigration,
    MigrationError,
    apply_domain_migrations,
    discover_domain_migrations,
)
from backend.scripts.run_domain_migrations import main
from backend.scripts import run_domain_migrations as runner_module
from backend.db.table_prefix import configure_table_prefix
from backend.db.table_prefix import prefixed_trigger_name, rewrite_sql
from backend.db.versioned_migrations import prepare_resumable_statement


ROOT = Path(__file__).resolve().parents[2]
SIMULATION_0033_COLUMNS = [
    ("parent_node_key", "varchar(128)", "utf8mb4", "utf8mb4_bin", "STORED GENERATED",
     "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.parent_occurrence_id')),'null')"),
    ("sibling_order", "int", None, None, "STORED GENERATED",
     "CAST(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.child_order')) AS UNSIGNED)"),
]


def _simulation_0033_create_table(rows, table):
    definitions = [f" `{row[0]}` {row[1]} GENERATED ALWAYS AS ({row[5]}) STORED,"
                   for row in rows]
    return f"CREATE TABLE `{table}` (\n" + "\n".join(definitions) + "\n)"


@pytest.fixture
def craft_manifest():
    return load_domain_manifests(
        ROOT / "backend/capability_v2/official_domains.json"
    ).require("craft")


@pytest.fixture
def simulation_manifest():
    return load_domain_manifests(
        ROOT / "backend/capability_v2/official_domains.json"
    ).require("simulation")


@pytest.fixture
def base_manifest():
    return load_domain_manifests(
        ROOT / "backend/capability_v2/official_domains.json"
    ).require("base")


def _migration_root(tmp_path: Path, craft_manifest) -> Path:
    path = tmp_path / craft_manifest.database.migration_path
    path.mkdir(parents=True)
    return path


def test_discovers_only_selected_domain_migrations(tmp_path, craft_manifest):
    path = _migration_root(tmp_path, craft_manifest)
    (path / "0001_initial.sql").write_text(
        "CREATE TABLE IF NOT EXISTS craft_versions (id VARCHAR(64) PRIMARY KEY);",
        encoding="utf-8",
    )
    other = tmp_path / "backend/db/migrations/domains/base"
    other.mkdir(parents=True)
    (other / "0001_initial.sql").write_text(
        "CREATE TABLE IF NOT EXISTS base_versions (id VARCHAR(64) PRIMARY KEY);",
        encoding="utf-8",
    )

    migrations = discover_domain_migrations(tmp_path, craft_manifest)

    assert [item.migration_id for item in migrations] == ["0001"]
    assert migrations[0].name == "initial"
    assert migrations[0].artifact_version == craft_manifest.artifact.version


def test_craft_migrations_add_pbom_updated_at(craft_manifest):
    migrations = discover_domain_migrations(ROOT, craft_manifest)

    assert any(
        "ALTER TABLE `workmanship_bop_pbom`" in item.sql
        and "ADD COLUMN IF NOT EXISTS `updated_at`" in item.sql
        for item in migrations
    )


def test_resource_requirement_backfill_qualifies_duplicate_gid(craft_manifest):
    migration = next(
        item for item in discover_domain_migrations(ROOT, craft_manifest)
        if item.migration_id == "0004"
    )

    assert "ON DUPLICATE KEY UPDATE `gid`=`gid`" not in migration.sql
    assert migration.sql.count(
        "ON DUPLICATE KEY UPDATE `resource_version`=`resource_version`"
    ) == 3


def test_rejects_cross_database_identifier(tmp_path, craft_manifest):
    path = _migration_root(tmp_path, craft_manifest)
    (path / "0001_initial.sql").write_text(
        "CREATE TABLE ai00_factory.assets (id VARCHAR(64));", encoding="utf-8"
    )

    with pytest.raises(MigrationError, match="cross_database_identifier"):
        discover_domain_migrations(tmp_path, craft_manifest)


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("CREATE DATABASE ai00_other;", "database_scope_forbidden"),
        ("USE ai00_craft;", "database_scope_forbidden"),
        ("GRANT SELECT ON craft_versions TO worker;", "database_privilege_forbidden"),
        ("ALTER TABLE craft_versions DROP COLUMN legacy;", "non-resumable"),
    ],
)
def test_rejects_unsafe_domain_migration_sql(tmp_path, craft_manifest, sql, reason):
    path = _migration_root(tmp_path, craft_manifest)
    (path / "0001_unsafe.sql").write_text(sql, encoding="utf-8")

    with pytest.raises(MigrationError, match=reason):
        discover_domain_migrations(tmp_path, craft_manifest)


def test_rejects_duplicate_ids_and_invalid_filenames(tmp_path, craft_manifest):
    path = _migration_root(tmp_path, craft_manifest)
    sql = "CREATE TABLE IF NOT EXISTS craft_versions (id VARCHAR(64) PRIMARY KEY);"
    (path / "0001_initial.sql").write_text(sql, encoding="utf-8")
    (path / "0001_second.sql").write_text(sql, encoding="utf-8")

    with pytest.raises(MigrationError, match="duplicate migration id"):
        discover_domain_migrations(tmp_path, craft_manifest)

    (path / "0001_second.sql").unlink()
    (path / "1_bad.sql").write_text(sql, encoding="utf-8")
    with pytest.raises(MigrationError, match="invalid migration filename"):
        discover_domain_migrations(tmp_path, craft_manifest)


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection
        self._one = None
        self._all = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.connection.statements.append((normalized, params))
        if "GET_LOCK" in normalized:
            self._one = (1,)
        elif normalized.startswith("SELECT migration_id"):
            self._all = list(self.connection.ledger_rows)
        elif "information_schema.TABLE_CONSTRAINTS" in normalized:
            self._one = (0,)
            if 'CHECK_CLAUSE' in normalized:
                self._all = list(self.connection.runtime_constraints)
        elif "information_schema.STATISTICS" in normalized:
            self._one = (0,)
        elif "information_schema.COLUMNS" in normalized:
            self._one = (0,)
        elif normalized == "SELECT VERSION()":
            self._one = ("OceanBase_CE 4.3.5.1",)
        elif "ADD CONSTRAINT" in normalized and "'cancelled'" in normalized:
            self.connection.runtime_constraints = [
                ('runtime_status', "status in ('queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired')"),
                ('sim_runtime_plan_status_recovery', "status in ('queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired','cancelled')"),
            ]
        elif "DROP CHECK sim_runtime_plan_status_pre_recovery" in normalized:
            self.connection.runtime_constraints = [
                item for item in self.connection.runtime_constraints
                if item[0] != 'runtime_status'
            ]

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class RecordingConnection:
    def __init__(self, ledger_rows=()):
        self.ledger_rows = ledger_rows
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.runtime_constraints = [
            ('runtime_status', "status in ('queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired')"),
        ]

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class OceanBaseNoNamedLockCursor(RecordingCursor):
    def execute(self, sql, params=()):
        if "GET_LOCK" in " ".join(sql.split()):
            raise RuntimeError(1305, "FUNCTION GET_LOCK does not exist")
        return super().execute(sql, params)


class OceanBaseNoNamedLockConnection(RecordingConnection):
    def cursor(self):
        return OceanBaseNoNamedLockCursor(self)


class ExistingPrefixedColumnCursor(RecordingCursor):
    def execute(self, sql, params=()):
        super().execute(sql, params)
        if "information_schema.COLUMNS" in " ".join(sql.split()):
            self._one = (1 if params[0] == "test_workmanship_sim_capture_requests" else 0,)


TRIGGER_ACTION = "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Historical upload provenance is append-only'"


class HistoricalTriggerCursor(RecordingCursor):
    def execute(self, sql, params=()):
        super().execute(sql, params)
        if "information_schema.TRIGGERS" in sql:
            name = params[0]
            trigger = self.connection.triggers.get(name)
            if "COUNT(*)" in sql:
                self._one = (int(trigger is not None),)
            else:
                self._all = [trigger] if trigger else []
        elif "CREATE TRIGGER" in sql:
            import re
            match = re.search(r"CREATE TRIGGER (\w+) BEFORE (UPDATE|DELETE)", sql)
            if match:
                name = prefixed_trigger_name(match.group(1))
                self.connection.triggers[name] = (
                    name, rewrite_sql("workmanship_base_historical_uploads"),
                    match.group(2), "BEFORE", "ROW", TRIGGER_ACTION,
                )


class HistoricalTriggerConnection(RecordingConnection):
    def __init__(self, triggers=None, ledger_rows=()):
        super().__init__(ledger_rows=ledger_rows)
        self.triggers = dict(triggers or {})

    def cursor(self):
        return HistoricalTriggerCursor(self)


def _expected_trigger(name, event):
    return (name, rewrite_sql("workmanship_base_historical_uploads"), event,
            "BEFORE", "ROW", TRIGGER_ACTION)


def test_base_0004_preserves_checksum_and_marks_only_frozen_trigger_sql(base_manifest, tmp_path):
    migration = next(item for item in discover_domain_migrations(ROOT, base_manifest)
                     if item.migration_id == "0004")
    assert migration.checksum == "8da1d92e0fb3743ab8034edf8d97cdcda0be1db48f2ba259aee196c5c7a31a61"
    assert migration.sql.count("AI00: RESUMABLE CREATE TRIGGER") == 2
    directory = tmp_path / base_manifest.database.migration_path
    directory.mkdir(parents=True)
    original = ROOT / base_manifest.database.migration_path / "0004_historical_uploads.sql"
    (directory / original.name).write_bytes(original.read_bytes().replace(
        b"append-only", b"append-only changed"))
    with pytest.raises(MigrationError, match="non-resumable"):
        discover_domain_migrations(tmp_path, base_manifest)


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_base_0004_resumes_only_missing_trigger_with_verified_definition(base_manifest, prefix):
    migration = next(item for item in discover_domain_migrations(ROOT, base_manifest)
                     if item.migration_id == "0004")
    configure_table_prefix(prefix)
    try:
        update_name = prefixed_trigger_name("base_historical_uploads_no_update")
        delete_name = prefixed_trigger_name("base_historical_uploads_no_delete")
        connection = HistoricalTriggerConnection({update_name: _expected_trigger(update_name, "UPDATE")})
        assert apply_domain_migrations(connection, base_manifest, (migration,)) == ("0004",)
        assert connection.triggers[delete_name] == _expected_trigger(delete_name, "DELETE")
        statements = [sql for sql, _ in connection.statements]
        assert not any(sql.startswith("CREATE TRIGGER base_historical_uploads_no_update") for sql in statements)
        assert len([sql for sql in statements if "CREATE TRIGGER base_historical_uploads_no_delete" in sql]) == 1
        probes = [params for sql, params in connection.statements if "information_schema.TRIGGERS" in sql]
        assert set(probes) == {(update_name,), (delete_name,)}
    finally:
        configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
@pytest.mark.parametrize("field,value", [
    (1, "other_table"), (2, "DELETE"), (3, "AFTER"), (4, "STATEMENT"),
    (5, "SET @anything=1"),
])
def test_base_0004_refuses_wrong_same_name_trigger_before_ddl(base_manifest, prefix, field, value):
    migration = next(item for item in discover_domain_migrations(ROOT, base_manifest)
                     if item.migration_id == "0004")
    configure_table_prefix(prefix)
    try:
        name = prefixed_trigger_name("base_historical_uploads_no_update")
        wrong = list(_expected_trigger(name, "UPDATE"))
        wrong[field] = value
        connection = HistoricalTriggerConnection({name: tuple(wrong)})
        with pytest.raises(MigrationError, match="historical_upload_trigger_definition_mismatch"):
            apply_domain_migrations(connection, base_manifest, (migration,))
        assert not any("CREATE TRIGGER" in sql for sql, _ in connection.statements)
    finally:
        configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
@pytest.mark.parametrize("present", [False, True])
def test_base_0004_applied_ledger_rejects_missing_or_changed_trigger(base_manifest, prefix, present):
    migration = next(item for item in discover_domain_migrations(ROOT, base_manifest)
                     if item.migration_id == "0004")
    configure_table_prefix(prefix)
    try:
        update_name = prefixed_trigger_name("base_historical_uploads_no_update")
        delete_name = prefixed_trigger_name("base_historical_uploads_no_delete")
        update = _expected_trigger(update_name, "UPDATE")
        if present:
            update = (*update[:5], "SET @anything=1")
        connection = HistoricalTriggerConnection({update_name: update,
            delete_name: _expected_trigger(delete_name, "DELETE")}, ledger_rows=({
                "migration_id": "0004", "checksum": migration.checksum,
                "artifact_version": migration.artifact_version,
            },))
        if not present:
            connection.triggers.pop(delete_name)
        with pytest.raises(MigrationError, match=("historical_upload_trigger_definition_mismatch" if present
                                                   else "historical_upload_triggers_missing")):
            apply_domain_migrations(connection, base_manifest, (migration,))
    finally:
        configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_base_0004_rechecks_new_trigger_before_ledger_insert(base_manifest, prefix):
    migration = next(item for item in discover_domain_migrations(ROOT, base_manifest)
                     if item.migration_id == "0004")

    class WrongCreatedCursor(HistoricalTriggerCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "CREATE TRIGGER base_historical_uploads_no_delete" in sql:
                name = prefixed_trigger_name("base_historical_uploads_no_delete")
                row = self.connection.triggers[name]
                self.connection.triggers[name] = (*row[:5], "SET @anything=1")

    class WrongCreatedConnection(HistoricalTriggerConnection):
        def cursor(self):
            return WrongCreatedCursor(self)

    configure_table_prefix(prefix)
    try:
        name = prefixed_trigger_name("base_historical_uploads_no_update")
        connection = WrongCreatedConnection({name: _expected_trigger(name, "UPDATE")})
        with pytest.raises(MigrationError, match="historical_upload_trigger_definition_mismatch"):
            apply_domain_migrations(connection, base_manifest, (migration,))
        assert not any(sql.startswith("INSERT INTO ai00_base_schema_migrations")
                       for sql, _ in connection.statements)
    finally:
        configure_table_prefix("")


def test_simulation_historical_0004_checksum_upgrades_through_current_chain(simulation_manifest):
    migrations = discover_domain_migrations(ROOT, simulation_manifest)
    old = next(item for item in migrations if item.migration_id == "0004")
    assert old.checksum == "be3e9cefefa42b1fc196ffdf275d4740d30d8acffff0e80dc0408008e03ada04"
    assert "ADD COLUMN IF NOT EXISTS" in old.sql
    assert ",\n  ADD COLUMN IF NOT EXISTS" not in old.sql
    ledger = tuple(
        {"migration_id": item.migration_id, "checksum": item.checksum,
         "artifact_version": item.artifact_version}
        for item in migrations if item.migration_id <= "0004"
    )
    connection = RecordingConnection(ledger_rows=ledger)

    applied = apply_domain_migrations(connection, simulation_manifest, migrations)

    assert applied == tuple(item.migration_id for item in migrations if item.migration_id > "0004")


def test_simulation_0033_preserves_checksum_with_replay_safe_executable(simulation_manifest):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")
    assert migration.checksum == "92b0b1d5fd7551dd96fd64a7dbf4d2b8da72ff2cda0822e2939864979ca31931"
    assert migration.sql.count("ADD COLUMN IF NOT EXISTS") == 2
    assert "CREATE INDEX IF NOT EXISTS ix_cloud_cache_parent_order" in migration.sql
    assert "CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_manifests" in migration.sql


def test_simulation_0033_drift_does_not_receive_historical_replay_exception(tmp_path, simulation_manifest):
    directory = tmp_path / simulation_manifest.database.migration_path
    directory.mkdir(parents=True)
    original = ROOT / simulation_manifest.database.migration_path / "0033_cloud_model_cache_pinned_query.sql"
    (directory / original.name).write_bytes(original.read_bytes().replace(
        b"ix_cloud_cache_parent_order", b"ix_cloud_cache_parent_order_changed"))
    with pytest.raises(MigrationError, match="non-resumable"):
        discover_domain_migrations(tmp_path, simulation_manifest)


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_simulation_0033_resumes_after_columns_and_index_commit(simulation_manifest, prefix):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")

    class ExistingMetadataCursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "SELECT COLUMN_NAME, COLUMN_TYPE" in sql:
                self._all = [row[:5] for row in SIMULATION_0033_COLUMNS]
            if sql.startswith("SHOW CREATE TABLE"):
                table = sql.split("`")[1]
                self._one = (table, _simulation_0033_create_table(SIMULATION_0033_COLUMNS, table))
            if "SELECT COLUMN_NAME, SEQ_IN_INDEX" in sql and params[1] == "ix_cloud_cache_parent_order":
                self._all = [(column, position, 1, None) for position, column in enumerate(
                    ("batch_id", "parent_node_key", "sibling_order", "node_key"), 1)]
            if ("information_schema.COLUMNS" in sql and
                    params[1] in {"parent_node_key", "sibling_order"}):
                self._one = (1,)
            if "information_schema.STATISTICS" in sql and params[1] == "ix_cloud_cache_parent_order":
                self._one = (1,)

    class ExistingMetadataConnection(RecordingConnection):
        def cursor(self):
            return ExistingMetadataCursor(self)

    connection = ExistingMetadataConnection()
    configure_table_prefix(prefix)
    try:
        assert apply_domain_migrations(connection, simulation_manifest, (migration,)) == ("0033",)
    finally:
        configure_table_prefix("")
    statements = [sql for sql, _ in connection.statements]
    metadata = [(sql, params) for sql, params in connection.statements
                if "information_schema.COLUMNS" in sql or "information_schema.STATISTICS" in sql]
    assert len(metadata) == 5
    assert all(params[0] == prefix + "workmanship_sim_cloud_cache_nodes"
               for _, params in metadata)
    assert not any(sql.startswith("ALTER TABLE workmanship_sim_cloud_cache_nodes") for sql in statements)
    assert not any(sql.startswith("CREATE INDEX ix_cloud_cache_parent_order") for sql in statements)
    assert any(sql.startswith("CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_manifests")
               for sql in statements)


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
@pytest.mark.parametrize("column, value", [
    ("parent_node_key", ("parent_node_key", "varchar(64)", "utf8mb4", "utf8mb4_bin", "STORED GENERATED",
                         SIMULATION_0033_COLUMNS[0][5])),
    ("parent_node_key", ("parent_node_key", "varchar(128)", "utf8mb4", "utf8mb4_general_ci",
                         "STORED GENERATED", SIMULATION_0033_COLUMNS[0][5])),
    ("sibling_order", ("sibling_order", "int", None, None, "VIRTUAL GENERATED",
                       SIMULATION_0033_COLUMNS[1][5])),
    ("sibling_order", ("sibling_order", "int", None, None, "STORED GENERATED",
                       "CAST(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.other_order')) AS UNSIGNED)")),
])
def test_simulation_0033_refuses_conflicting_generated_column_before_ddl(
    simulation_manifest, prefix, column, value,
):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")

    class ConflictingColumnCursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "SELECT COLUMN_NAME, COLUMN_TYPE" in sql:
                self._all = [value[:5]]
            if sql.startswith("SHOW CREATE TABLE"):
                table = sql.split("`")[1]
                self._one = (table, _simulation_0033_create_table([value], table))
            if "information_schema.COLUMNS" in sql and "COUNT(*)" in sql:
                self._one = (1 if params[1] == column else 0,)

    class ConflictingColumnConnection(RecordingConnection):
        def cursor(self):
            return ConflictingColumnCursor(self)

    connection = ConflictingColumnConnection()
    configure_table_prefix(prefix)
    try:
        with pytest.raises(MigrationError, match="simulation_0033_column_definition_mismatch"):
            apply_domain_migrations(connection, simulation_manifest, (migration,))
    finally:
        configure_table_prefix("")
    assert not any(sql.startswith("ALTER TABLE workmanship_sim_cloud_cache_nodes") or
                   sql.startswith("INSERT INTO ai00_simulation_schema_migrations")
                   for sql, _ in connection.statements)
    assert any("SELECT COLUMN_NAME, COLUMN_TYPE" in sql and params[0] ==
               prefix + "workmanship_sim_cloud_cache_nodes" for sql, params in connection.statements)


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_simulation_0033_applied_ledger_requires_both_generated_columns(simulation_manifest, prefix):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")

    class MissingColumnCursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "SELECT COLUMN_NAME, COLUMN_TYPE" in sql:
                self._all = [SIMULATION_0033_COLUMNS[0][:5]]
            if sql.startswith("SHOW CREATE TABLE"):
                table = sql.split("`")[1]
                self._one = (table, _simulation_0033_create_table(SIMULATION_0033_COLUMNS[:1], table))

    class MissingColumnConnection(RecordingConnection):
        def cursor(self):
            return MissingColumnCursor(self)

    connection = MissingColumnConnection(ledger_rows=({
        "migration_id": "0033", "checksum": migration.checksum,
        "artifact_version": migration.artifact_version,
    },))
    configure_table_prefix(prefix)
    try:
        with pytest.raises(MigrationError, match="simulation_0033_columns_missing"):
            apply_domain_migrations(connection, simulation_manifest, (migration,))
    finally:
        configure_table_prefix("")
    assert not any(sql.startswith("INSERT INTO ai00_simulation_schema_migrations")
                   for sql, _ in connection.statements)


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_simulation_0033_refuses_crossed_show_create_table(simulation_manifest, prefix):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")

    class CrossedMetadataCursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "SELECT COLUMN_NAME, COLUMN_TYPE" in sql:
                self._all = [row[:5] for row in SIMULATION_0033_COLUMNS]
            if sql.startswith("SHOW CREATE TABLE"):
                other = ("pp_" if prefix == "test_" else "test_") + "workmanship_sim_cloud_cache_nodes"
                self._one = (other, _simulation_0033_create_table(SIMULATION_0033_COLUMNS, other))

    class CrossedMetadataConnection(RecordingConnection):
        def cursor(self):
            return CrossedMetadataCursor(self)

    connection = CrossedMetadataConnection()
    configure_table_prefix(prefix)
    try:
        with pytest.raises(MigrationError, match="simulation_0033_column_definition_mismatch"):
            apply_domain_migrations(connection, simulation_manifest, (migration,))
    finally:
        configure_table_prefix("")
    assert not any(sql.startswith("ALTER TABLE workmanship_sim_cloud_cache_nodes") or
                   sql.startswith("INSERT INTO ai00_simulation_schema_migrations")
                   for sql, _ in connection.statements)


def test_simulation_0033_accepts_matching_show_create_expression_with_charset_introducer(simulation_manifest):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")

    class NormalizedMetadataCursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "SELECT COLUMN_NAME, COLUMN_TYPE" in sql:
                self._all = [row[:5] for row in SIMULATION_0033_COLUMNS]
            if sql.startswith("SHOW CREATE TABLE"):
                table = sql.split("`")[1]
                ddl = _simulation_0033_create_table(SIMULATION_0033_COLUMNS, table)
                ddl = ddl.replace("data_json", "`data_json`").replace("'$.structure.", "_utf8mb4'$.structure.")
                ddl = ddl.replace("'null'", "_utf8mb4'null'")
                self._one = (table, ddl)
            if "SELECT COLUMN_NAME, SEQ_IN_INDEX" in sql:
                self._all = [(column, position, 1, None) for position, column in enumerate(
                    ("batch_id", "parent_node_key", "sibling_order", "node_key"), 1)]

    class NormalizedMetadataConnection(RecordingConnection):
        def cursor(self):
            return NormalizedMetadataCursor(self)

    connection = NormalizedMetadataConnection(ledger_rows=({
        "migration_id": "0033", "checksum": migration.checksum,
        "artifact_version": migration.artifact_version,
    },))
    configure_table_prefix("test_")
    try:
        assert apply_domain_migrations(connection, simulation_manifest, (migration,)) == ()
    finally:
        configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
@pytest.mark.parametrize("columns, non_unique", [
    (("batch_id", "node_key", "sibling_order", "parent_node_key"), 1),
    (("batch_id", "parent_node_key", "sibling_order", "node_key"), 0),
])
def test_simulation_0033_refuses_conflicting_named_index_before_ddl(
    simulation_manifest, prefix, columns, non_unique,
):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")

    class ConflictingIndexCursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "SELECT COLUMN_NAME, SEQ_IN_INDEX" in sql:
                self._all = [(column, position, non_unique, None)
                             for position, column in enumerate(columns, 1)]

    class ConflictingIndexConnection(RecordingConnection):
        def cursor(self):
            return ConflictingIndexCursor(self)

    connection = ConflictingIndexConnection()
    configure_table_prefix(prefix)
    try:
        with pytest.raises(MigrationError, match="simulation_0033_index_definition_mismatch"):
            apply_domain_migrations(connection, simulation_manifest, (migration,))
    finally:
        configure_table_prefix("")
    statements = [sql for sql, _ in connection.statements]
    assert not any(sql.startswith("ALTER TABLE workmanship_sim_cloud_cache_nodes") for sql in statements)
    assert not any(sql.startswith("CREATE INDEX ix_cloud_cache_parent_order") for sql in statements)
    assert not any(sql.startswith("INSERT INTO ai00_simulation_schema_migrations") for sql in statements)


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
@pytest.mark.parametrize("index_rows, error", [
    ([], "simulation_0033_index_missing"),
    ([("batch_id", 1, 1, None), ("node_key", 2, 1, None)],
     "simulation_0033_index_definition_mismatch"),
])
def test_simulation_0033_applied_ledger_still_requires_matching_physical_index(
    simulation_manifest, prefix, index_rows, error,
):
    migration = next(item for item in discover_domain_migrations(ROOT, simulation_manifest)
                     if item.migration_id == "0033")

    class AppliedIndexCursor(RecordingCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "SELECT COLUMN_NAME, COLUMN_TYPE" in sql:
                self._all = [row[:5] for row in SIMULATION_0033_COLUMNS]
            if sql.startswith("SHOW CREATE TABLE"):
                table = sql.split("`")[1]
                self._one = (table, _simulation_0033_create_table(SIMULATION_0033_COLUMNS, table))
            if "SELECT COLUMN_NAME, SEQ_IN_INDEX" in sql:
                self._all = index_rows

    class AppliedIndexConnection(RecordingConnection):
        def cursor(self):
            return AppliedIndexCursor(self)

    connection = AppliedIndexConnection(ledger_rows=({
        "migration_id": "0033", "checksum": migration.checksum,
        "artifact_version": migration.artifact_version,
    },))
    configure_table_prefix(prefix)
    try:
        with pytest.raises(MigrationError, match=error):
            apply_domain_migrations(connection, simulation_manifest, (migration,))
    finally:
        configure_table_prefix("")
    assert not any(sql.startswith("INSERT INTO ai00_simulation_schema_migrations")
                   for sql, _ in connection.statements)


def test_apply_uses_domain_lock_ledger_and_artifact_version(craft_manifest):
    migration = DomainMigration(
        migration_id="0001",
        name="initial",
        path=Path("0001_initial.sql"),
        sql="CREATE TABLE IF NOT EXISTS craft_versions (id VARCHAR(64) PRIMARY KEY)",
        checksum="a" * 64,
        artifact_version=craft_manifest.artifact.version,
    )
    connection = RecordingConnection()

    applied = apply_domain_migrations(connection, craft_manifest, (migration,))

    assert applied == ("0001",)
    assert any("CREATE TABLE IF NOT EXISTS ai00_craft_schema_migrations" in sql for sql, _ in connection.statements)
    assert any(params == ("ai00:migrations:craft:v1", 30) for sql, params in connection.statements if "GET_LOCK" in sql)
    ledger_insert = next(
        (sql, params) for sql, params in connection.statements
        if sql.startswith("INSERT INTO ai00_craft_schema_migrations")
    )
    assert "artifact_version" in ledger_insert[0]
    assert ledger_insert[1] == (
        "0001",
        "initial",
        "a" * 64,
        craft_manifest.artifact.version,
    )
    assert any("RELEASE_LOCK" in sql for sql, _ in connection.statements)


def test_apply_falls_back_when_oceanbase_has_no_named_lock(craft_manifest):
    migration = DomainMigration(
        migration_id="0001",
        name="initial",
        path=Path("0001_initial.sql"),
        sql="CREATE TABLE IF NOT EXISTS craft_versions (id VARCHAR(64) PRIMARY KEY)",
        checksum="a" * 64,
        artifact_version=craft_manifest.artifact.version,
    )
    connection = OceanBaseNoNamedLockConnection()

    assert apply_domain_migrations(connection, craft_manifest, (migration,)) == ("0001",)
    assert not any("RELEASE_LOCK" in sql for sql, _ in connection.statements)


def test_domains_use_distinct_migration_ledgers(craft_manifest, simulation_manifest):
    migration = lambda manifest: DomainMigration(
        migration_id="0001",
        name="initial",
        path=Path("0001_initial.sql"),
        sql="CREATE TABLE IF NOT EXISTS owned_table (id VARCHAR(64) PRIMARY KEY)",
        checksum="a" * 64,
        artifact_version=manifest.artifact.version,
    )
    craft_connection = RecordingConnection()
    simulation_connection = RecordingConnection()

    apply_domain_migrations(craft_connection, craft_manifest, (migration(craft_manifest),))
    apply_domain_migrations(
        simulation_connection, simulation_manifest, (migration(simulation_manifest),)
    )

    assert any("ai00_craft_schema_migrations" in sql for sql, _ in craft_connection.statements)
    assert any(
        "ai00_simulation_schema_migrations" in sql
        for sql, _ in simulation_connection.statements
    )


def test_resumable_column_probe_honors_active_table_prefix():
    connection = RecordingConnection()
    connection.cursor = lambda: ExistingPrefixedColumnCursor(connection)
    configure_table_prefix("test_")
    try:
        prepared = prepare_resumable_statement(
            connection,
            "ALTER TABLE workmanship_sim_capture_requests "
            "ADD COLUMN IF NOT EXISTS plan_json JSON NULL",
        )
    finally:
        configure_table_prefix("")

    assert prepared is None


def test_marked_foreign_key_drop_is_replay_safe_when_constraint_is_absent(craft_manifest):
    migration = DomainMigration(
        migration_id="0002",
        name="drop_legacy_fk",
        path=Path("0002_drop_legacy_fk.sql"),
        sql=(
            "-- AI00: RESUMABLE DROP FOREIGN KEY\n"
            "ALTER TABLE craft_versions DROP FOREIGN KEY craft_versions_ibfk_1;"
        ),
        checksum="b" * 64,
        artifact_version=craft_manifest.artifact.version,
    )
    connection = RecordingConnection()

    assert apply_domain_migrations(connection, craft_manifest, (migration,)) == ("0002",)
    assert any("information_schema.TABLE_CONSTRAINTS" in sql for sql, _ in connection.statements)
    assert not any(sql.startswith("ALTER TABLE craft_versions DROP FOREIGN KEY") for sql, _ in connection.statements)


def test_socket_resource_backfill_is_a_follow_up_migration(craft_manifest):
    migration = next(
        item for item in discover_domain_migrations(ROOT, craft_manifest)
        if item.migration_id == "0006"
    )

    assert "'socket'" in migration.sql
    assert "socket_model" in migration.sql
    assert "socket_cad_no" in migration.sql
    assert "GROUP BY" in migration.sql.upper()
    assert "FROM `workmanship_tpl_vpps_tools`" in migration.sql
    assert "ON DUPLICATE KEY UPDATE `resource_version`=`resource_version`" in migration.sql


def test_apply_rejects_changed_checksum_for_applied_migration(craft_manifest):
    migration = DomainMigration(
        migration_id="0001",
        name="initial",
        path=Path("0001_initial.sql"),
        sql="CREATE TABLE IF NOT EXISTS craft_versions (id VARCHAR(64) PRIMARY KEY)",
        checksum="a" * 64,
        artifact_version=craft_manifest.artifact.version,
    )
    connection = RecordingConnection(
        ledger_rows=({"migration_id": "0001", "checksum": "b" * 64},)
    )

    with pytest.raises(MigrationError, match="checksum changed"):
        apply_domain_migrations(connection, craft_manifest, (migration,))


def test_check_mode_validates_empty_domain_without_connecting(capsys):
    assert main(["--domain", "craft", "--check"], root=ROOT, environ={}) == 0
    assert capsys.readouterr().out.strip() == "domain=craft migrations=13 mode=check"


def test_apply_requires_only_the_selected_domains_ddl_credential(monkeypatch, capsys):
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    captured = []
    monkeypatch.setattr(
        runner_module,
        "connect_domain_database",
        lambda url: captured.append(url) or connection,
        raising=False,
    )
    monkeypatch.setattr(
        runner_module,
        "verify_live_server",
        lambda _connection: {"version": "OceanBase_CE 4.3.5.1"},
    )
    monkeypatch.setattr(
        runner_module,
        "apply_domain_migrations",
        lambda _connection, _manifest, _migrations: (),
    )

    result = main(
        ["--domain", "craft", "--apply"],
        root=ROOT,
        environ={
            "AI00_CRAFT_DDL_DB_URL": "mysql://craft_ddl:secret@db/ai00_craft",
        },
    )

    assert result == 0
    assert captured[0].username == "craft_ddl"
    assert connection.closed is True
    assert "domain=craft migrations=13 applied=0" in capsys.readouterr().out


def test_apply_configures_selected_table_prefix(monkeypatch, capsys, simulation_manifest):
    class Connection:
        def close(self):
            pass

    prefixes = []
    monkeypatch.setattr(runner_module, "configure_table_prefix", prefixes.append)
    monkeypatch.setattr(runner_module, "connect_domain_database", lambda _url: Connection())
    monkeypatch.setattr(
        runner_module,
        "verify_live_server",
        lambda _connection: {"version": "OceanBase_CE 4.3.5.1"},
    )
    monkeypatch.setattr(
        runner_module,
        "apply_domain_migrations",
        lambda _connection, _manifest, _migrations: (),
    )

    result = main(
        ["--domain", "simulation", "--apply"],
        root=ROOT,
        environ={
            "AI00_SIMULATION_DDL_DB_URL":
                "mysql://simulation_ddl:secret@db/sht_mes_tool",
            "TABLE_PREFIX": "test_",
        },
    )

    assert result == 0
    assert prefixes == ["test_"]
    assert f"domain=simulation migrations={len(discover_domain_migrations(ROOT, simulation_manifest))} applied=0" in capsys.readouterr().out


@pytest.mark.parametrize(("profile", "prefix", "url"), [
    ("production", "test_", "https://workmanship-backend.chehejia.com"),
    ("test", "pp_", "http://127.0.0.1:8080"),
    ("", "pp_", "https://workmanship-backend.chehejia.com"),
])
def test_domain_migration_refuses_wrong_profile_before_connection(monkeypatch, profile, prefix, url):
    monkeypatch.setattr(runner_module, "connect_domain_database", lambda _url: pytest.fail("database connection attempted"))
    with pytest.raises(SystemExit, match="profile|ENV_FILE|prefix"):
        main(["--domain", "craft", "--apply"], root=ROOT, environ={
            "AI00_CRAFT_DDL_DB_URL": "mysql://ddl:secret@db.example/ai00",
            "AI00_DEPLOY_PROFILE": profile, "TABLE_PREFIX": prefix, "PUBLIC_URL": url,
        })


def test_domain_migration_env_file_cannot_inherit_production_profile(monkeypatch, tmp_path):
    env_file = tmp_path / "domain.env"
    env_file.write_text(
        "TABLE_PREFIX=pp_\nPUBLIC_URL=https://workmanship-backend.chehejia.com\n"
        "AI00_CRAFT_DDL_DB_URL=mysql://ddl:secret@db.example/ai00\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner_module, "connect_domain_database", lambda _url: pytest.fail("database connection attempted"))
    with pytest.raises(SystemExit, match="managed_deployment_requires_explicit_profile"):
        main(["--domain", "craft", "--apply"], root=ROOT, environ={
            "ENV_FILE": str(env_file), "AI00_DEPLOY_PROFILE": "production",
        })


@pytest.mark.parametrize("mode", ["--check", "--apply"])
def test_domain_migration_refuses_duplicate_env_before_connection(monkeypatch, tmp_path, mode):
    env_file = tmp_path / "domain.env"
    env_file.write_text("AI00_DEPLOY_PROFILE=test\nTABLE_PREFIX=test_\n"
                        "PUBLIC_URL=http://127.0.0.1:8080\n"
                        "AI00_REQUIRE_MIGRATIONS=0\nAI00_REQUIRE_MIGRATIONS=1\n", encoding="utf-8")
    monkeypatch.setattr(runner_module, "connect_domain_database",
                        lambda _url: pytest.fail("database connection attempted"))
    with pytest.raises(SystemExit, match="duplicate"):
        main(["--domain", "craft", mode], root=ROOT, environ={"ENV_FILE": str(env_file)})


def test_domain_migration_refuses_linked_env_before_connection(monkeypatch, tmp_path):
    env_file = tmp_path / "domain.env"
    env_file.write_text("AI00_DEPLOY_PROFILE=test", encoding="utf-8")
    original = type(env_file).lstat
    monkeypatch.setattr(type(env_file), "lstat", lambda path: SimpleNamespace(st_mode=stat.S_IFLNK)
                        if path == env_file else original(path))
    with pytest.raises(SystemExit, match="missing or invalid"):
        main(["--domain", "craft", "--check"], root=ROOT, environ={"ENV_FILE": str(env_file)})
