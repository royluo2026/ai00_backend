import json
from pathlib import Path

from backend.capability_v2.schema_compiler import compile_expected_schema
from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.domain_migrations import discover_domain_migrations
from backend.governance import load_registry


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend/db/migrations/domains/agent/0005_agent_orchestration_mvp.sql"
RUNTIME_MIGRATION = ROOT / "backend/db/migrations/domains/agent/0006_agent_orchestration_runtime_metrics.sql"
TABLES = {
    "workmanship_agent_orch_panoramas",
    "workmanship_agent_orch_versions",
    "workmanship_agent_orch_axis_views",
    "workmanship_agent_orch_business_nodes",
    "workmanship_agent_orch_flow_edges",
    "workmanship_agent_orch_items",
    "workmanship_agent_orch_item_edges",
    "workmanship_agent_orch_capability_bindings",
    "workmanship_agent_orch_context_bindings",
}
RUNTIME_TABLES = {
    "workmanship_agent_orch_runs",
    "workmanship_agent_orch_run_events",
    "workmanship_agent_orch_workload_baselines",
    "workmanship_agent_orch_acceptance_facts",
    "workmanship_agent_orch_metric_snapshots",
}


def test_authoritative_agent_schema_contains_all_orchestration_tables():
    schema = compile_expected_schema(ROOT)
    names = {table.name for table in schema.tables}

    assert TABLES | RUNTIME_TABLES <= names


def test_domain_runner_discovers_orchestration_migrations():
    manifest = load_domain_manifests(
        ROOT / "backend/capability_v2/official_domains.json"
    ).require("agent")

    migrations = discover_domain_migrations(ROOT, manifest)

    assert [item.migration_id for item in migrations][-2:] == ["0004", "0005"]


def test_orchestration_schema_is_agent_owned_and_replay_safe():
    sql = MIGRATION.read_text(encoding="utf-8")
    inventory = json.loads(
        (ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )
    owners = {row["table"]: row["owner"] for row in inventory["tables"]}

    assert all(f"CREATE TABLE IF NOT EXISTS {table}" in sql for table in TABLES)
    assert all(owners.get(table) == "agent" for table in TABLES)
    registry = load_registry()
    assert all(registry.table_owner(table).owner == "agent" for table in TABLES)
    assert inventory["table_count"] == len(inventory["tables"])
    assert "REFERENCES workmanship_" not in sql
    assert "DEFAULT (JSON_" not in sql


def test_runtime_metrics_schema_is_agent_owned_and_keeps_external_refs_soft():
    sql = RUNTIME_MIGRATION.read_text(encoding="utf-8")
    inventory = json.loads(
        (ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )
    owners = {row["table"]: row["owner"] for row in inventory["tables"]}

    assert all(f"CREATE TABLE IF NOT EXISTS {table}" in sql for table in RUNTIME_TABLES)
    assert all(owners.get(table) == "agent" for table in RUNTIME_TABLES)
    registry = load_registry()
    assert all(registry.table_owner(table).owner == "agent" for table in RUNTIME_TABLES)
    assert "REFERENCES workmanship_" not in sql
