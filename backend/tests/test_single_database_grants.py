import json
from pathlib import Path

import pytest

from backend.scripts.generate_domain_grants import (
    GrantPolicyError, build_domain_grant_plan,
)
from backend.governance import load_registry
from backend.scripts.verify_single_database_grants import verify_grant_rows


ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS = {domain: f"user_{domain}" for domain in load_registry().product_domains}


def _inventory():
    return json.loads((ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8"))


def test_domain_grants_partition_all_owned_tables_without_ddl():
    inventory = _inventory()
    plan = build_domain_grant_plan(ACCOUNTS, inventory)
    assert sum(len(item.tables) for item in plan.accounts) == len(inventory["tables"])
    assert all(item.privileges == ("SELECT", "INSERT", "UPDATE", "DELETE") for item in plan.accounts)


def test_developer_account_cannot_receive_foreign_domain_table():
    inventory = _inventory()
    inventory["tables"][0] = {**inventory["tables"][0], "runtime_domain": "device"}
    with pytest.raises(GrantPolicyError, match="inventory ownership mismatch"):
        build_domain_grant_plan(ACCOUNTS, inventory)


@pytest.mark.parametrize("grant", [
    "GRANT CREATE ON ai00_test.* TO 'runtime'@'%'",
    "GRANT ALL PRIVILEGES ON *.* TO 'runtime'@'%'",
    "GRANT SELECT ON ai00_test.* TO 'runtime'@'%' WITH GRANT OPTION",
])
def test_verifier_rejects_ddl_wildcards_and_grant_option(grant):
    result = verify_grant_rows([grant], expected_tables=(), account_label="runtime")
    assert result.passed is False
    assert result.failures


def test_verifier_reports_missing_and_extra_tables_without_account_values():
    result = verify_grant_rows([
        "GRANT USAGE ON *.* TO 'secret-account-name'@'%'",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON `ai00_test`.`workmanship_device_assets` TO 'secret-account-name'@'%'",
    ], expected_tables=("workmanship_device_expected",), account_label="device")
    output = result.to_dict()
    assert output["missing_tables"] == ["workmanship_device_expected"]
    assert output["extra_tables"] == ["workmanship_device_assets"]
    assert "secret-account-name" not in json.dumps(output)
