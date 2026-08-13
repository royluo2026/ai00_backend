import json
from pathlib import Path

from backend.scripts.generate_domain_grants import DEVELOPER_GROUPS, render_grouped_grants


ROOT = Path(__file__).resolve().parents[2]


def _section(sql: str, group: str) -> str:
    marker = f"-- account-group:{group}\n"
    body = sql.split(marker, 1)[1]
    return body.split("\n-- account-group:", 1)[0]


def test_four_developer_groups_and_runtime_receive_only_expected_tables():
    inventory = json.loads(
        (ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )
    accounts = {
        "craft": "ai00_dev_craft",
        "model_simulation": "ai00_dev_model_sim",
        "device": "ai00_dev_device",
        "shared": "ai00_dev_shared",
        "runtime": "ai00_runtime",
    }

    sql = render_grouped_grants(
        inventory,
        database="ai00_test",
        host="%",
        accounts=accounts,
        include_revokes=True,
    )

    assert DEVELOPER_GROUPS["model_simulation"] == ("digital_model", "simulation")
    assert "workmanship_craft_" in _section(sql, "craft")
    assert "workmanship_model_" in _section(sql, "model_simulation")
    assert "workmanship_sim_" in _section(sql, "model_simulation")
    assert "workmanship_runtime_devices" in _section(sql, "device")
    assert "workmanship_plugin_namespace_kv" in _section(sql, "shared")
    assert "workmanship_runtime_devices" in _section(sql, "runtime")
    assert "workmanship_model_models" not in _section(sql, "craft").split("REVOKE", 1)[0]
    assert all(keyword not in sql.upper() for keyword in ("CREATE ", "ALTER ", "DROP "))


def test_group_account_names_are_validated():
    inventory = json.loads(
        (ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )
    accounts = {group: "valid_user" for group in (*DEVELOPER_GROUPS, "runtime")}
    accounts["device"] = "bad'user"

    try:
        render_grouped_grants(inventory, database="ai00_test", host="%", accounts=accounts)
    except ValueError as exc:
        assert "invalid account" in str(exc)
    else:
        raise AssertionError("unsafe account was accepted")
