import json
from pathlib import Path

import pytest

from backend.governance import load_registry
from backend.scripts.generate_domain_grants import render_domain_grants


ROOT = Path(__file__).resolve().parents[2]


def _section(sql: str, domain: str) -> str:
    marker = f"-- runtime-domain:{domain}\n"
    body = sql.split(marker, 1)[1]
    return body.split("\n-- runtime-domain:", 1)[0]


def test_eleven_domain_accounts_receive_only_prefixed_owned_tables():
    inventory = json.loads(
        (ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )
    accounts = {domain: f"user_{domain}" for domain in load_registry().product_domains}

    sql = render_domain_grants(
        inventory,
        database="workmanship",
        table_prefix="test_",
        host="%",
        accounts=accounts,
        include_revokes=True,
    )

    assert sql.count("-- runtime-domain:") == 11
    assert "`test_workmanship_craft_" in _section(sql, "craft")
    assert "`test_workmanship_model_" in _section(sql, "digital_model")
    assert "`test_workmanship_sim_" in _section(sql, "simulation")
    assert "`test_workmanship_runtime_devices`" in _section(sql, "device")
    assert "`test_workmanship_plugin_namespace_kv`" in _section(sql, "base")
    assert "`test_workmanship_model_models`" not in _section(sql, "craft").split("REVOKE", 1)[0]
    assert not any(keyword in line for line in sql.splitlines() if line.startswith("GRANT ")
                   for keyword in (" CREATE ", " ALTER ", " DROP "))


def test_domain_account_names_are_validated():
    inventory = json.loads(
        (ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )
    accounts = {domain: f"user_{domain}" for domain in load_registry().product_domains}
    accounts["device"] = "bad'user"
    with pytest.raises(ValueError, match="invalid account"):
        render_domain_grants(inventory, database="workmanship", table_prefix="pp_",
                             host="%", accounts=accounts)
