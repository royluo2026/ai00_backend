from __future__ import annotations

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
