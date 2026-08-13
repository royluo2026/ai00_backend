#!/usr/bin/env python3
"""Generate (never execute) least-privilege OceanBase/MySQL grants."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.governance import load_registry

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_$.-]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9_$%.:-]+$")

DEVELOPER_GROUPS = {
    "craft": ("craft",),
    "model_simulation": ("digital_model", "simulation"),
    "device": ("device",),
    "shared": (
        "base",
        "project_management",
        "factory",
        "knowledge",
        "ontology",
        "agent",
        "integration",
    ),
}

DML_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")


class GrantPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class AccountGrantPlan:
    label: str
    account: str
    tables: tuple[str, ...]
    privileges: tuple[str, ...] = DML_PRIVILEGES


@dataclass(frozen=True)
class GroupedGrantPlan:
    accounts: tuple[AccountGrantPlan, ...]

    def require(self, label: str) -> AccountGrantPlan:
        return next(item for item in self.accounts if item.label == label)


def build_grouped_grant_plan(accounts: dict[str, str], inventory: dict) -> GroupedGrantPlan:
    required = set(DEVELOPER_GROUPS) | {"runtime"}
    if set(accounts) != required:
        raise GrantPolicyError(f"account groups must be exactly: {sorted(required)}")
    validated_accounts = {label: checked(value, ACCOUNT_RE, "account") for label, value in accounts.items()}
    if len(set(validated_accounts.values())) != len(accounts):
        raise GrantPolicyError("account groups require distinct accounts")
    domain_groups = {domain: group for group, domains in DEVELOPER_GROUPS.items() for domain in domains}
    tables = inventory.get("tables", [])
    for row in tables:
        owner, runtime = row.get("owner"), row.get("runtime_domain")
        if owner not in domain_groups or runtime != owner:
            raise GrantPolicyError(f"group_scope_violation:{row.get('table')}")
    plans = []
    for label in (*DEVELOPER_GROUPS, "runtime"):
        domains = set(DEVELOPER_GROUPS.get(label, domain_groups))
        selected = tuple(sorted(row["table"] for row in tables if label == "runtime" or row["owner"] in domains))
        plans.append(AccountGrantPlan(label, validated_accounts[label], selected))
    return GroupedGrantPlan(tuple(plans))


def checked(value: str, regex: re.Pattern, label: str) -> str:
    if not regex.fullmatch(value):
        raise ValueError(f"invalid {label}: {value!r}")
    return value


def parse_accounts(values: list[str], required: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"account must be domain=user form: {value}")
        domain, account = value.split("=", 1)
        if domain not in required:
            raise ValueError(f"unknown runtime domain: {domain}")
        result[domain] = checked(account, ACCOUNT_RE, "account")
    missing = required - set(result)
    if missing:
        raise ValueError(f"missing accounts for: {sorted(missing)}")
    return result


def _grant_line(database: str, table: str, account: str, host: str) -> str:
    return (
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{database}`.`{table}` "
        f"TO '{account}'@'{host}';"
    )


def render_grouped_grants(
    inventory: dict,
    *,
    database: str,
    host: str,
    accounts: dict[str, str],
    include_revokes: bool = False,
) -> str:
    database = checked(database, IDENTIFIER_RE, "database")
    host = checked(host, HOST_RE, "host")
    tables = inventory.get("tables", [])
    if any(not item.get("owner") or not item.get("runtime_domain") for item in tables):
        raise ValueError("inventory contains unowned tables")
    all_tables = sorted(str(item["table"]) for item in tables)
    for table in all_tables:
        checked(table, IDENTIFIER_RE, "table")

    lines = [
        "-- Generated desired DML grants. Review before execution.",
        "-- Schema changes require the external migration identity.",
    ]
    plan = build_grouped_grant_plan(accounts, inventory)
    for group in (*DEVELOPER_GROUPS, "runtime"):
        account_plan = plan.require(group)
        account, allowed = account_plan.account, account_plan.tables
        lines.extend(("", f"-- account-group:{group}"))
        lines.extend(_grant_line(database, table, account, host) for table in allowed)
        if include_revokes:
            foreign = sorted(set(all_tables) - set(allowed))
            lines.extend(
                f"REVOKE ALL PRIVILEGES ON `{database}`.`{table}` "
                f"FROM '{account}'@'{host}';"
                for table in foreign
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "backend/governance/table_inventory.json")
    parser.add_argument("--database", required=True)
    parser.add_argument("--host", default="%")
    parser.add_argument("--account", action="append", default=[], metavar="DOMAIN=USER")
    parser.add_argument("--account-group", action="append", default=[], metavar="GROUP=USER")
    parser.add_argument("--include-revokes", action="store_true")
    args = parser.parse_args()

    database = checked(args.database, IDENTIFIER_RE, "database")
    host = checked(args.host, HOST_RE, "host")
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    registry = load_registry()
    if inventory.get("registry_version") != registry.version:
        raise ValueError("inventory registry version is stale")
    if args.account_group:
        if args.account:
            raise ValueError("choose --account-group or --account, not both")
        accounts = parse_accounts(
            args.account_group,
            set(DEVELOPER_GROUPS) | {"runtime"},
        )
        print(
            render_grouped_grants(
                inventory,
                database=database,
                host=host,
                accounts=accounts,
                include_revokes=args.include_revokes,
            ),
            end="",
        )
        return 0

    runtime_domains = set(registry.product_domains)
    accounts = parse_accounts(args.account, runtime_domains)
    tables = inventory.get("tables", [])
    if any(not item.get("owner") or not item.get("runtime_domain") for item in tables):
        raise ValueError("inventory contains unowned tables")

    lines = [
        "-- Generated desired grants. Review before execution.",
        "-- DDL is intentionally absent from all runtime accounts.",
    ]
    for domain in sorted(runtime_domains):
        account = accounts[domain]
        owned = sorted(item["table"] for item in tables if item["runtime_domain"] == domain)
        lines.append(f"\n-- {domain}")
        for table in owned:
            checked(table, IDENTIFIER_RE, "table")
            lines.append(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{database}`.`{table}` TO '{account}'@'{host}';"
            )
        if args.include_revokes:
            foreign = sorted(item["table"] for item in tables if item["runtime_domain"] != domain)
            for table in foreign:
                checked(table, IDENTIFIER_RE, "table")
                lines.append(
                    f"REVOKE ALL PRIVILEGES ON `{database}`.`{table}` FROM '{account}'@'{host}';"
                )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
