from __future__ import annotations

import subprocess
from pathlib import Path

from backend.db.versioned_migrations import discover_migrations, validate_migration
from backend.governance import load_registry


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "backend/db/migrations"
BASELINE = "7f86507e"


def _git_bytes(revision: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def test_0005_stays_immutable_and_0006_is_oceanbase_safe_and_base_owned():
    path = "backend/db/migrations/202608280005_base_structural_owner_hardening.sql"
    assert (ROOT / path).read_bytes() == _git_bytes(BASELINE, path)

    repair = next(item for item in discover_migrations(MIGRATIONS) if item.migration_id == "202608280006")
    validate_migration(repair, load_registry())


def test_0006_reconciles_historical_replay_and_audit_tenants_from_aggregate_then_actor():
    repair = (MIGRATIONS / "202608280006_base_historical_tenant_repair.sql").read_text(encoding="utf-8").lower()

    for table, aggregate, row_id in (
        ("workmanship_base_saved_view_idempotency", "workmanship_app_view_configs", "view_gid"),
        ("workmanship_base_saved_view_audit_events", "workmanship_app_view_configs", "view_gid"),
        ("workmanship_base_self_annotation_idempotency", "workmanship_base_self_annotations", "item_gid"),
        ("workmanship_base_self_annotation_audit_events", "workmanship_base_self_annotations", "item_gid"),
    ):
        assert f"update {table}" in repair
        assert aggregate in repair
        assert row_id in repair

    assert repair.count("workmanship_auth_users") >= 4
    assert repair.count("legacy-unresolved:") >= 4
    assert repair.count("concat('user:',") >= 4
    assert "workmanship_base_schema_migrations" in repair
    assert "migration_id='202608280006'" in repair
