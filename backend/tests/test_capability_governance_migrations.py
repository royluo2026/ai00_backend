from __future__ import annotations

import json
import os
import subprocess
import sys
import re
import pytest
from pathlib import Path

from backend.scripts.migrate_capability_governance_test import (
    GOVERNANCE_TABLES,
    compile_governance_migrations,
)


ROOT = Path(__file__).resolve().parents[2]


def test_shared_test_schema_prefixes_backfill_dependencies_and_preserves_checksums():
    original = compile_governance_migrations(ROOT)
    isolated = compile_governance_migrations(ROOT, table_prefix="test_")
    assert all(name.startswith("test_workmanship_") for name in isolated.tables)
    assert not re.search(r"(?<![A-Za-z0-9_])workmanship_", isolated.normalized_sql)
    assert "JOIN test_workmanship_base_capability_catalog_releases" in isolated.normalized_sql
    assert [m.checksum for m in original.migrations] == [m.checksum for m in isolated.migrations]


@pytest.mark.parametrize("prefix", ["prod_", "test_unsafe;", "test_other_", " test_", None])
def test_governance_migration_rejects_unrecognized_namespace(prefix):
    from backend.db.versioned_migrations import MigrationError
    with pytest.raises(MigrationError, match="table prefix"):
        compile_governance_migrations(ROOT, table_prefix=prefix)


@pytest.mark.parametrize("missing_named_lock", [False, True])
def test_shared_test_apply_never_probes_or_writes_unprefixed_tables(missing_named_lock):
    from backend.scripts.migrate_capability_governance_test import migrate

    class RecordingConnection:
        def __init__(self):
            self.statements = []
        def cursor(self):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, sql, args=None):
            self.statements.append((sql, args))
            if missing_named_lock and "GET_LOCK" in sql:
                raise RuntimeError(1305, "FUNCTION GET_LOCK does not exist")
        def fetchone(self):
            return (1,) if "GET_LOCK" in self.statements[-1][0] else (0,)
        def commit(self):
            pass
        def rollback(self):
            pass

    connection = RecordingConnection()
    applied = migrate(connection, table_prefix="test_", externally_serialized=missing_named_lock)
    assert len(applied) == 9
    assert connection.statements[0][1] == ("ai00:capability-governance:test:v1:test_", 30)
    if not missing_named_lock:
        assert connection.statements[-1][1] == ("ai00:capability-governance:test:v1:test_",)
    else:
        assert not any("RELEASE_LOCK" in sql for sql, _ in connection.statements)
    assert any(args == ("test_workmanship_base_capability_governance_migrations",)
               for _, args in connection.statements)
    assert sum(sql.startswith("INSERT INTO test_workmanship_base_capability_governance_migrations")
               for sql, _ in connection.statements) == 9
    for sql, args in connection.statements:
        assert not re.search(r"(?<![A-Za-z0-9_])workmanship_", sql)
        if "information_schema" in sql:
            assert args[0].startswith("test_workmanship_")

EXPECTED_TABLES = {
    "workmanship_base_capability_entries",
    "workmanship_base_capability_versions",
    "workmanship_base_capability_scan_runs",
    "workmanship_base_capability_snapshots",
    "workmanship_base_capability_snapshot_entries",
    "workmanship_base_capability_implementation_nodes",
    "workmanship_base_capability_bindings",
    "workmanship_base_capability_implementation_relations",
    "workmanship_base_capability_evidence",
    "workmanship_base_capability_test_runs",
    "workmanship_base_capability_test_results",
    "workmanship_base_capability_health_rollups",
    "workmanship_base_capability_analysis_runs",
    "workmanship_base_capability_findings",
    "workmanship_base_capability_finding_subjects",
    "workmanship_base_capability_change_proposals",
    "workmanship_base_capability_reviews",
    "workmanship_base_capability_waivers",
    "workmanship_base_capability_release_reports",
    "workmanship_base_capability_audit_events",
    "workmanship_base_capability_worker_leases",
    "workmanship_base_capability_business_purposes",
    "workmanship_base_capability_business_rules",
    "workmanship_base_capability_relation_candidates",
    "workmanship_base_capability_business_reviews",
    "workmanship_base_capability_business_review_requests",
    "workmanship_base_capability_standard_review_requests",
    "workmanship_base_capability_rule_effectiveness",
}


@pytest.mark.parametrize("code,external", [(1305, False), (1205, True), (1045, True)])
def test_migration_lock_errors_fail_before_any_ddl(code, external):
    from backend.scripts.migrate_capability_governance_test import migrate
    statements = []
    class RefusingConnection:
        def cursor(self):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, sql, args=None):
            statements.append(sql)
            raise RuntimeError(code, "GET_LOCK failure")
    with pytest.raises(RuntimeError):
        migrate(RefusingConnection(), table_prefix="test_", externally_serialized=external)
    assert statements == ["SELECT GET_LOCK(%s, %s)"]


def test_test_governance_schema_is_complete_and_oceanbase_safe():
    compiled = compile_governance_migrations(ROOT)

    assert set(compiled.tables) == EXPECTED_TABLES
    assert set(GOVERNANCE_TABLES) == EXPECTED_TABLES
    assert " ENGINE=" not in compiled.normalized_sql.upper()
    assert " JSON " not in compiled.normalized_sql.upper()
    assert " ON DELETE CASCADE" not in compiled.normalized_sql.upper()
    assert "LONGTEXT" in compiled.normalized_sql.upper()


def test_test_governance_migrations_are_separate_from_product_schema_compilation():
    compiled = compile_governance_migrations(ROOT)

    assert all("test_governance" in str(migration.path) for migration in compiled.migrations)


def test_test_governance_migration_ledger_has_authoritative_ownership():
    ledger = "workmanship_base_capability_governance_migrations"
    ownership = json.loads(
        (ROOT / "backend/governance/domain_table_ownership.json").read_text(encoding="utf-8")
    )
    inventory = json.loads(
        (ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )

    assert ledger in {item["table"] for item in ownership["tables"]}
    assert ledger in {item["table"] for item in inventory["tables"]}


def test_worker_leases_have_an_explicit_test_governance_table():
    compiled = compile_governance_migrations(ROOT)

    assert "CREATE TABLE IF NOT EXISTS workmanship_base_capability_worker_leases" in compiled.normalized_sql


def test_business_governance_hash_columns_are_binary_exact():
    compiled = compile_governance_migrations(ROOT)
    migration = next(item for item in compiled.migrations if item.migration_id == "0006")
    sql = migration.sql.upper()

    assert sql.count("DEFINITION_HASH VARBINARY(71) NOT NULL") == 4
    assert "CANDIDATE_HASH VARBINARY(71) NOT NULL" in sql


def test_snapshot_catalog_hash_uses_the_next_unique_resumable_migration():
    compiled = compile_governance_migrations(ROOT)
    ids = [item.migration_id for item in compiled.migrations]
    migration = next(item for item in compiled.migrations if item.migration_id == "0009")

    assert len(ids) == len(set(ids))
    assert migration.path.name == "0009_snapshot_catalog_hash.sql"
    assert "-- AI00: RESUMABLE BACKFILL" in migration.sql
    assert "ON BINARY catalog.release_id = BINARY snapshot.catalog_release_id" in migration.sql
    assert "WHERE snapshot.catalog_hash IS NULL" in migration.sql
    assert "MODIFY COLUMN catalog_hash VARCHAR(71) NOT NULL" in migration.sql


def test_cli_failure_redacts_configuration_and_traceback():
    environment = os.environ.copy()
    environment["AI00_DEPLOYMENT_PROFILE"] = "test-governance"
    environment["AI00_BASE_DDL_DB_URL"] = "mysql://migration:topsecret@db/ai00_test"

    completed = subprocess.run(
        [sys.executable, str(ROOT / "backend/scripts/migrate_capability_governance_test.py"), "--apply"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert completed.stderr == "capability governance migration command failed\n"
    assert "topsecret" not in completed.stderr
    assert "Traceback" not in completed.stderr
