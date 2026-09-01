from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from backend.scripts.migrate_capability_governance_test import (
    GOVERNANCE_TABLES,
    compile_governance_migrations,
)


ROOT = Path(__file__).resolve().parents[2]

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
