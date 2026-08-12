from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _reviewed_tables() -> set[str]:
    review = json.loads(
        (ROOT / "docs/governance/capability-coverage-review/project-management.json")
        .read_text(encoding="utf-8")
    )
    return {item["table"] for item in review["database_boundaries"]}


def test_project_management_has_an_independent_complete_migration_stream():
    migration = (
        ROOT
        / "backend/db/migrations/domains/project_management/0001_project_management.sql"
    )

    assert migration.is_file()
    sql = migration.read_text(encoding="utf-8")
    assert "workmanship_project_management_schema_migrations" in sql
    assert _reviewed_tables() <= {
        line.split("`", 2)[1]
        for line in sql.splitlines()
        if line.startswith("CREATE TABLE IF NOT EXISTS `")
    }


def test_project_migration_does_not_claim_craft_tables():
    migration = (
        ROOT
        / "backend/db/migrations/domains/project_management/0001_project_management.sql"
    )

    sql = migration.read_text(encoding="utf-8")
    assert "workmanship_bop_" not in sql
    assert "workmanship_ontology_" not in sql
    assert "workmanship_sim_" not in sql
