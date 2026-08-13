from __future__ import annotations

import json
from pathlib import Path

from backend.governance import load_registry
from backend.scripts.audit_domain_boundaries import audit_sql_text


ROOT = Path(__file__).resolve().parents[2]
TABLE_INVENTORY = ROOT / "backend/governance/table_inventory.json"
TABLE_OWNERSHIP = ROOT / "backend/governance/domain_table_ownership.json"


def test_every_discovered_table_has_one_exact_owner():
    registry = load_registry()
    inventory = json.loads(TABLE_INVENTORY.read_text(encoding="utf-8"))
    exact = json.loads(TABLE_OWNERSHIP.read_text(encoding="utf-8"))

    assert len(exact["tables"]) == len({item["table"] for item in exact["tables"]})
    assert {item["table"] for item in exact["tables"]} == {
        item["table"] for item in inventory["tables"]
    }
    assert all(item["table"].startswith("workmanship_") for item in exact["tables"])
    assert all(registry.table_owner(item["table"]) is not None for item in exact["tables"])


def test_prefix_match_does_not_implicitly_own_a_new_table():
    registry = load_registry()

    assert registry.table_owner("workmanship_craft_unregistered_future") is None


def test_cross_domain_foreign_key_is_rejected_even_in_one_database():
    violations = audit_sql_text(
        "CREATE TABLE workmanship_device_bid (model_gid VARCHAR(64), "
        "FOREIGN KEY (model_gid) REFERENCES workmanship_model_models(gid))",
        path="backend/db/migrations/domains/device/0002_bid.sql",
        registry=load_registry(),
    )

    assert [item.category for item in violations] == ["cross_domain_foreign_key"]
