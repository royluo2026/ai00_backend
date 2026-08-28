from __future__ import annotations

import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

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


def _historical_rows():
    from backend.db.base_historical_tenant_repair import REPAIR_TABLES

    records = {}
    for table in REPAIR_TABLES:
        aggregate_field = "view_gid" if "saved_view" in table.name else "item_gid"
        rows = []
        for label, actor_gid in (
            ("team", "actor-team"),
            ("person", "actor-person"),
            ("unknown", "actor-unknown"),
            ("precedence", "actor-precedence"),
        ):
            row = {"tenant_gid": f"user:{actor_gid}", "actor_gid": actor_gid, aggregate_field: f"{aggregate_field}-{label}"}
            if table.is_idempotency:
                row.update({"operation": "change.apply", "idempotency_key": f"key-{label}"})
            else:
                row["gid"] = f"{table.name}-{label}"
            rows.append(row)
        records[table.name] = rows
    return records


def _tenant_fixture():
    return {
        "records": _historical_rows(),
        "saved_views": {
            "view_gid-team": "team-from-view",
            "view_gid-precedence": "team-from-view-precedence",
        },
        "annotations": {
            ("item_gid-team", "actor-team"): "team-from-annotation",
            ("item_gid-precedence", "actor-precedence"): "team-from-annotation-precedence",
        },
        "users": {
            "actor-team": "team-from-user",
            "actor-person": None,
            "actor-precedence": "team-from-user-precedence",
        },
    }


def test_executable_0006_fixture_repairs_all_tables_and_is_replay_safe():
    from backend.db.base_historical_tenant_repair import apply_tenant_repair, legacy_unresolved_scope

    fixture = _tenant_fixture()
    assert apply_tenant_repair(**fixture, marker_applied=False) == 12

    for table, rows in fixture["records"].items():
        assert [row["tenant_gid"] for row in rows[:2]] == [
            "team-from-view" if "saved_view" in table else "team-from-annotation",
            "user:actor-person",
        ]
        assert rows[2]["tenant_gid"] == legacy_unresolved_scope(table, rows[2])
        assert rows[2]["tenant_gid"].startswith("legacy-unresolved:")
        assert rows[3]["tenant_gid"] == (
            "team-from-view-precedence" if "saved_view" in table else "team-from-annotation-precedence"
        )

    assert apply_tenant_repair(**fixture, marker_applied=False) == 0
    assert apply_tenant_repair(**fixture, marker_applied=True) == 0


def test_executable_0006_fixture_resumes_partial_work_and_fails_closed_on_primary_key_collision():
    from backend.db.base_historical_tenant_repair import REPAIR_TABLES, TenantRepairCollision, apply_tenant_repair

    fixture = _tenant_fixture()
    partial = tuple(table.name for table in REPAIR_TABLES[:2])
    assert apply_tenant_repair(**fixture, marker_applied=False, tables=partial) == 6
    assert apply_tenant_repair(**fixture, marker_applied=False) == 6
    assert apply_tenant_repair(**fixture, marker_applied=False) == 0

    collision = _tenant_fixture()
    collision_table = REPAIR_TABLES[0].name
    collision["records"][collision_table].append({
        "tenant_gid": "team-from-view", "actor_gid": "actor-team", "view_gid": "view_gid-team",
        "operation": "change.apply", "idempotency_key": "key-team",
    })
    before = deepcopy(collision["records"])
    with pytest.raises(TenantRepairCollision, match=collision_table):
        apply_tenant_repair(**collision, marker_applied=False, tables=(collision_table,))
    assert collision["records"] == before


@pytest.mark.parametrize(
    "module_name,repository_name,error_name",
    [
        ("backend.base.saved_views", "SqlSavedViewRepository", "SavedViewError"),
        ("backend.base.self_annotations", "SqlSelfAnnotationRepository", "SelfAnnotationError"),
    ],
)
def test_synthetic_legacy_digest_fails_closed_as_idempotency_conflict(monkeypatch, module_name, repository_name, error_name):
    from contextlib import contextmanager
    from backend.db.base_historical_tenant_repair import legacy_synthetic_digest

    module = __import__(module_name, fromlist=[error_name])
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            pass

        def fetchone(self):
            return {"command_digest": legacy_synthetic_digest("actor-team", "change.apply", "key-team"), "status": "completed", "result_json": "{}"}

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_get_conn():
        yield Connection()

    monkeypatch.setattr(module, "get_conn", fake_get_conn)
    repository = getattr(module, repository_name)()
    with pytest.raises(getattr(module, error_name)) as caught:
        with repository.transaction():
            repository.claim(
                tenant_gid="team-from-view", actor_gid="actor-team", operation="change.apply",
                idempotency_key="key-team", command_digest="canonical-new-command-digest",
            )
    assert caught.value.code == "idempotency_conflict"


def test_0006_is_the_checked_in_render_of_the_executable_repair_plan():
    from backend.db.base_historical_tenant_repair import render_migration_sql

    assert (MIGRATIONS / "202608280006_base_historical_tenant_repair.sql").read_text(encoding="utf-8") == render_migration_sql()
