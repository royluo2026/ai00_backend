from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.scripts.migrate_connector_to_simulation import (
    MigrationConflict,
    migrate_connector_rows,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONNECTOR_TABLES = {
    "workmanship_sim_connector_bindings",
    "workmanship_sim_connector_enrollments",
    "workmanship_sim_connector_legacy_commands",
    "workmanship_sim_connector_health",
    "workmanship_sim_connector_heartbeat_audit",
    "workmanship_sim_connector_plans",
    "workmanship_sim_connector_projection_outbox",
    "workmanship_sim_connector_pairings",
}


class MemoryRowStore:
    def __init__(self, tables: dict[str, list[dict]] | None = None) -> None:
        self.tables = deepcopy(tables or {})

    def read_rows(self, table: str) -> tuple[dict, ...]:
        return tuple(deepcopy(self.tables.get(table, ())))

    def read_row(self, table: str, key: tuple[object, ...]) -> dict | None:
        for row in self.tables.get(table, ()):
            if _row_key(table, row) == key:
                return deepcopy(row)
        return None

    def insert_row(self, table: str, row: dict) -> None:
        self.tables.setdefault(table, []).append(deepcopy(row))

    def replace(self, table: str, key: tuple[object, ...], row: dict) -> None:
        rows = self.tables.setdefault(table, [])
        rows[:] = [item for item in rows if _row_key(table, item) != key]
        rows.append(deepcopy(row))


def _row_key(table: str, row: dict) -> tuple[object, ...]:
    fields = {
        "workmanship_sim_connector_bindings": ("connector_id",),
        "workmanship_sim_connector_enrollments": ("gid",),
        "workmanship_sim_connector_legacy_commands": ("gid",),
        "workmanship_sim_connector_health": ("connector_id",),
        "workmanship_sim_connector_heartbeat_audit": ("gid",),
        "workmanship_sim_connector_plans": ("plan_id",),
        "workmanship_sim_connector_projection_outbox": (
            "plan_id", "outcome_hash", "target_capability",
        ),
    }[table]
    return tuple(row[field] for field in fields)


def _source_rows() -> dict[str, list[dict]]:
    return {
        "workmanship_runtime_devices": [{
            "gid": "connector-1",
            "owner_user_gid": "user-1",
            "team_gid": "team-1",
            "display_name": "工位 A",
            "platform": "windows",
            "runtime_version": "1.0.0",
            "token_hash": "a" * 64,
            "capabilities": ["ai00.vismockup@1"],
            "status": "online",
            "last_seen_at": "2026-09-03T12:00:00+00:00",
        }],
        "workmanship_device_connector_plans": [{
            "plan_id": "plan-1",
            "device_gid": "connector-1",
            "tenant_gid": "team-1",
            "user_gid": "user-1",
            "plan_hash": "sha256:" + "b" * 64,
            "plan_json": {"plan_id": "plan-1"},
            "status": "completed",
            "attempts": 1,
            "lease_id": "lease-1",
            "outcome_json": {"status": "completed"},
            "outcome_hash": "sha256:" + "c" * 64,
        }],
    }


def test_connector_migration_is_idempotent_and_hash_equal() -> None:
    source = MemoryRowStore(_source_rows())
    target = MemoryRowStore()

    first = migrate_connector_rows(source, target)
    second = migrate_connector_rows(source, target)

    assert first.source_counts == first.target_counts
    assert first.source_hashes == first.target_hashes
    assert second == first
    binding = target.tables["workmanship_sim_connector_bindings"][0]
    assert binding["connector_id"] == "connector-1"
    assert "gid" not in binding
    assert target.tables["workmanship_sim_connector_plans"][0]["plan_id"] == "plan-1"
    assert target.tables["workmanship_sim_connector_plans"][0]["connector_id"] == "connector-1"
    assert "device_gid" not in target.tables["workmanship_sim_connector_plans"][0]


def test_connector_migration_rejects_conflicting_target() -> None:
    source = MemoryRowStore(_source_rows())
    target = MemoryRowStore()
    migrate_connector_rows(source, target)
    conflicting = deepcopy(target.tables["workmanship_sim_connector_bindings"][0])
    conflicting["owner_user_gid"] = "other-user"
    target.replace(
        "workmanship_sim_connector_bindings", ("connector-1",), conflicting,
    )

    with pytest.raises(
        MigrationConflict,
        match="workmanship_sim_connector_bindings:connector-1",
    ):
        migrate_connector_rows(source, target)


def test_target_only_default_columns_do_not_create_false_conflicts() -> None:
    source = MemoryRowStore(_source_rows())
    target = MemoryRowStore()
    migrate_connector_rows(source, target)
    target.tables["workmanship_sim_connector_bindings"][0].update({
        "installation_id": None,
        "windows_sid_hash": None,
    })

    repeated = migrate_connector_rows(source, target)

    assert repeated.source_counts == repeated.target_counts
    assert repeated.source_hashes == repeated.target_hashes


def test_projection_attempt_rows_collapse_to_one_durable_intent() -> None:
    rows = _source_rows()
    rows["workmanship_device_connector_projection_outbox"] = [
        {
            "plan_id": "plan-1",
            "outcome_hash": "sha256:" + "c" * 64,
            "target_capability": "simulation.connector_capture_outcome.apply",
            "attempt": 1,
            "status": "retryable_failed",
        },
        {
            "plan_id": "plan-1",
            "outcome_hash": "sha256:" + "c" * 64,
            "target_capability": "simulation.connector_capture_outcome.apply",
            "attempt": 2,
            "status": "projected",
        },
    ]
    source = MemoryRowStore(rows)
    target = MemoryRowStore()

    first = migrate_connector_rows(source, target)
    repeated = migrate_connector_rows(source, target)

    migrated = target.tables["workmanship_sim_connector_projection_outbox"]
    assert len(migrated) == 1
    assert migrated[0]["attempt"] == 2
    assert first == repeated


def test_connector_tables_are_declared_in_simulation_migration_and_ownership() -> None:
    migration = (
        REPO_ROOT
        / "backend/db/migrations/domains/simulation/0005_connector_control_plane.sql"
    ).read_text(encoding="utf-8")
    ownership = json.loads(
        (REPO_ROOT / "backend/governance/domain_table_ownership.json").read_text(
            encoding="utf-8",
        )
    )
    rows = {item["table"]: item for item in ownership["tables"]}

    assert CONNECTOR_TABLES == {
        table for table in CONNECTOR_TABLES if f"`{table}`" in migration
    }
    assert CONNECTOR_TABLES == {
        table
        for table in CONNECTOR_TABLES
        if rows.get(table, {}).get("owner") == "simulation"
        and rows[table].get("runtime_domain") == "simulation"
    }
