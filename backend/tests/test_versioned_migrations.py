from __future__ import annotations

import subprocess
import re
from pathlib import Path

import pytest

from backend.db.table_prefix import configure_table_prefix, prefixed_trigger_name, rewrite_sql
from backend.db.versioned_migrations import apply_migrations, discover_migrations
from backend.db.versioned_migrations import MigrationError, HISTORICAL_UPLOAD_MIGRATION


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "backend/db/migrations"
HISTORICAL_0004 = "242f329f"


def _git_bytes(revision: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def test_applied_0004_checksum_remains_the_historical_object_checksum():
    """A database ledger created at 242f329f must accept the checked-in 0004."""
    path = "backend/db/migrations/202608280004_base_plugin_lifecycle_idempotency_scope.sql"
    current = (ROOT / path).read_bytes()

    assert current.replace(b"\r\n", b"\n").replace(b"\r", b"\n") == _git_bytes(HISTORICAL_0004, path)
    migration = next(item for item in discover_migrations(MIGRATIONS) if item.migration_id == "202608280004")
    assert migration.checksum == __import__("hashlib").sha256(current.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def test_upgrade_chain_contains_one_forward_only_historical_tenant_repair():
    migrations = discover_migrations(MIGRATIONS)

    assert [item.migration_id for item in migrations if item.migration_id <= "202609010003"][-6:] == [
        "202608280005",
        "202608280006",
        "202608310001",
        "202609010001",
        "202609010002",
        "202609010003",
    ]
    repair = next(item for item in migrations if item.migration_id == "202608280006")
    assert repair.name == "historical_tenant_repair"
    assert "202608280006" in repair.sql


def test_upgrade_chain_adds_forward_only_craft_rule_identity_compatibility():
    migration = next(
        item for item in discover_migrations(MIGRATIONS)
        if item.migration_id == "202609010001"
    )

    assert migration.migration_id == "202609010001"
    assert migration.name == "rule_identity_compatibility"
    assert "ADD COLUMN IF NOT EXISTS creator_gid" in migration.sql


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.one = None
        self.all = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.connection.statements.append((normalized, params))
        if "GET_LOCK" in normalized:
            self.one = (1,)
        elif normalized.startswith("SELECT migration_id"):
            self.all = list(self.connection.ledger.values())
        elif "information_schema.COLUMNS" in normalized:
            self.one = (0,) if "COUNT(*)" in normalized else ("YES",)
        elif "information_schema.STATISTICS" in normalized:
            self.one = (0,) if "COUNT(*)" in normalized else None
            self.all = []
        elif "information_schema.TRIGGERS" in normalized:
            trigger = self.connection.triggers.get(params[0])
            self.one = (int(trigger is not None),)
            self.all = [trigger] if trigger else []
        elif "CREATE TRIGGER" in normalized:
            match = re.search(r"CREATE TRIGGER (\w+) BEFORE (UPDATE|DELETE)", normalized)
            if match:
                name = prefixed_trigger_name(match.group(1))
                self.connection.triggers[name] = (
                    name, rewrite_sql("workmanship_base_historical_uploads"), match.group(2),
                    "BEFORE", "ROW", "SIGNAL SQLSTATE '45000' SET "
                    "MESSAGE_TEXT='Historical upload provenance is append-only'",
                )
        elif normalized.startswith("INSERT INTO workmanship_base_schema_migrations"):
            self.connection.ledger[params[0]] = {
                "migration_id": params[0],
                "checksum": params[3],
                "status": "applied",
            }

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.all


class _Connection:
    def __init__(self, ledger=()):
        self.ledger = {row["migration_id"]: row for row in ledger}
        self.statements = []
        self.triggers = {}

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_pre_0004_and_original_0004_ledgers_apply_only_the_forward_migrations_once():
    migrations = discover_migrations(MIGRATIONS)
    old_0004 = next(item for item in migrations if item.migration_id == "202608280004")
    prior_ledger = tuple(
        {"migration_id": item.migration_id, "checksum": item.checksum, "status": "applied"}
        for item in migrations
        if item.migration_id < "202608280004"
    )

    for ledger, expected in (
        (prior_ledger, [item.migration_id for item in migrations if item.migration_id >= "202608280004"]),
        (prior_ledger + ({"migration_id": "202608280004", "checksum": old_0004.checksum, "status": "applied"},),
         [item.migration_id for item in migrations if item.migration_id > "202608280004"]),
    ):
        connection = _Connection(ledger)
        assert apply_migrations(connection, directory=MIGRATIONS) == expected
        assert apply_migrations(connection, directory=MIGRATIONS) == []
        assert any("information_schema.COLUMNS" in sql for sql, _ in connection.statements)


def _single_historical_migration(tmp_path):
    source = MIGRATIONS / "202609080002_base_historical_uploads.sql"
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    return target


def _historical_trigger(name, event):
    return (name, rewrite_sql("workmanship_base_historical_uploads"), event, "BEFORE", "ROW",
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Historical upload provenance is append-only'")


def test_global_historical_upload_sql_rejects_checksum_drift_before_database_access(tmp_path):
    assert next(migration for migration in discover_migrations(MIGRATIONS)
                if migration.migration_id == HISTORICAL_UPLOAD_MIGRATION[0]).checksum == HISTORICAL_UPLOAD_MIGRATION[1]
    target = _single_historical_migration(tmp_path)
    target.write_bytes(target.read_bytes().replace(b"append-only", b"append-only changed"))
    connection = _Connection()
    with pytest.raises(MigrationError, match="historical_upload_migration_checksum_changed"):
        apply_migrations(connection, directory=tmp_path)
    assert connection.statements == []


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_global_historical_upload_resumes_partial_trigger_and_checks_applied_ledger(tmp_path, prefix):
    _single_historical_migration(tmp_path)
    configure_table_prefix(prefix)
    try:
        update_name = prefixed_trigger_name("base_historical_uploads_no_update")
        delete_name = prefixed_trigger_name("base_historical_uploads_no_delete")
        connection = _Connection()
        connection.triggers[update_name] = _historical_trigger(update_name, "UPDATE")
        assert apply_migrations(connection, directory=tmp_path) == [HISTORICAL_UPLOAD_MIGRATION[0]]
        assert connection.triggers[delete_name] == _historical_trigger(delete_name, "DELETE")
        assert apply_migrations(connection, directory=tmp_path) == []
        statements = [sql for sql, _ in connection.statements]
        assert not any("CREATE TRIGGER base_historical_uploads_no_update" in sql for sql in statements)
        assert len([sql for sql in statements if "CREATE TRIGGER base_historical_uploads_no_delete" in sql]) == 1
    finally:
        configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
@pytest.mark.parametrize("changed", [False, True])
def test_global_historical_upload_applied_ledger_refuses_missing_or_changed_trigger(tmp_path, prefix, changed):
    _single_historical_migration(tmp_path)
    configure_table_prefix(prefix)
    try:
        update_name = prefixed_trigger_name("base_historical_uploads_no_update")
        delete_name = prefixed_trigger_name("base_historical_uploads_no_delete")
        connection = _Connection(({
            "migration_id": HISTORICAL_UPLOAD_MIGRATION[0],
            "checksum": HISTORICAL_UPLOAD_MIGRATION[1], "status": "applied",
        },))
        connection.triggers[update_name] = _historical_trigger(update_name, "UPDATE")
        if changed:
            connection.triggers[delete_name] = (*_historical_trigger(delete_name, "DELETE")[:5], "SET @anything=1")
        with pytest.raises(MigrationError, match=("historical_upload_trigger_definition_mismatch" if changed
                                                   else "historical_upload_triggers_missing")):
            apply_migrations(connection, directory=tmp_path)
    finally:
        configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_global_historical_upload_refuses_wrong_existing_trigger_before_ddl(tmp_path, prefix):
    _single_historical_migration(tmp_path)
    configure_table_prefix(prefix)
    try:
        name = prefixed_trigger_name("base_historical_uploads_no_update")
        connection = _Connection()
        row = _historical_trigger(name, "UPDATE")
        connection.triggers[name] = (row[0], "other_table", *row[2:])
        with pytest.raises(MigrationError, match="historical_upload_trigger_definition_mismatch"):
            apply_migrations(connection, directory=tmp_path)
        assert not any("CREATE TRIGGER" in sql for sql, _ in connection.statements)
        assert any("'failed'" in sql for sql, _ in connection.statements
                   if sql.startswith("INSERT INTO workmanship_base_schema_migrations"))
    finally:
        configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_global_historical_upload_rechecks_new_trigger_before_applied_ledger(tmp_path, prefix):
    _single_historical_migration(tmp_path)

    class ChangedCursor(_Cursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "CREATE TRIGGER base_historical_uploads_no_delete" in sql:
                name = prefixed_trigger_name("base_historical_uploads_no_delete")
                self.connection.triggers[name] = (*self.connection.triggers[name][:5], "SET @anything=1")

    class ChangedConnection(_Connection):
        def cursor(self):
            return ChangedCursor(self)

    configure_table_prefix(prefix)
    try:
        update_name = prefixed_trigger_name("base_historical_uploads_no_update")
        connection = ChangedConnection()
        connection.triggers[update_name] = _historical_trigger(update_name, "UPDATE")
        with pytest.raises(MigrationError, match="historical_upload_trigger_definition_mismatch"):
            apply_migrations(connection, directory=tmp_path)
        assert not any("'applied'" in sql for sql, _ in connection.statements
                       if sql.startswith("INSERT INTO workmanship_base_schema_migrations"))
    finally:
        configure_table_prefix("")
