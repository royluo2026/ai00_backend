from __future__ import annotations

from pathlib import Path

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


ROOT = Path(__file__).resolve().parents[2]


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
        elif "information_schema.COLUMNS" in normalized:
            self._one = (0,)

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

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_simulation_historical_0004_checksum_upgrades_forward_to_0006(simulation_manifest):
    migrations = discover_domain_migrations(ROOT, simulation_manifest)
    old = next(item for item in migrations if item.migration_id == "0004")
    assert old.checksum == "be3e9cefefa42b1fc196ffdf275d4740d30d8acffff0e80dc0408008e03ada04"
    assert "ADD COLUMN IF NOT EXISTS" in old.sql
    ledger = tuple(
        {"migration_id": item.migration_id, "checksum": item.checksum,
         "artifact_version": item.artifact_version}
        for item in migrations if item.migration_id <= "0004"
    )
    connection = RecordingConnection(ledger_rows=ledger)

    applied = apply_domain_migrations(connection, simulation_manifest, migrations)

    assert applied == ("0005", "0006")


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
    assert any("CREATE TABLE IF NOT EXISTS ai00_schema_migrations" in sql for sql, _ in connection.statements)
    assert any(params == ("ai00:migrations:craft:v1", 30) for sql, params in connection.statements if "GET_LOCK" in sql)
    ledger_insert = next(
        (sql, params) for sql, params in connection.statements
        if sql.startswith("INSERT INTO ai00_schema_migrations")
    )
    assert "artifact_version" in ledger_insert[0]
    assert ledger_insert[1] == (
        "0001",
        "initial",
        "a" * 64,
        craft_manifest.artifact.version,
    )
    assert any("RELEASE_LOCK" in sql for sql, _ in connection.statements)


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
    assert capsys.readouterr().out.strip() == "domain=craft migrations=6 mode=check"


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
    assert "domain=craft migrations=6 applied=0" in capsys.readouterr().out
