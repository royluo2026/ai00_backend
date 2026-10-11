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
from backend.db.table_prefix import validate_runtime_profile
from backend.scripts.audit_domain_boundaries import audit_repository
from backend.scripts.runtime_preflight import read_controlled_values
from backend.scripts.verify_domain_db_isolation import URLS, _params

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_$.-]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9_$%.:-]+$")

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
class DomainGrantPlan:
    accounts: tuple[AccountGrantPlan, ...]

    def require(self, label: str) -> AccountGrantPlan:
        return next(item for item in self.accounts if item.label == label)


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
        if domain in result:
            raise GrantPolicyError(f"duplicate account domain: {domain}")
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


def build_domain_grant_plan(accounts: dict[str, str], inventory: dict, registry=None) -> DomainGrantPlan:
    registry = registry or load_registry()
    domains = set(registry.product_domains)
    if set(accounts) != domains:
        raise GrantPolicyError("exactly one account binding per runtime domain is required")
    for account in accounts.values():
        checked(account, ACCOUNT_RE, "account")
    rows = inventory.get("tables")
    if (inventory.get("registry_version") != registry.version or not isinstance(rows, list)
            or inventory.get("table_count") != len(rows)
            or len(rows) != registry._table_ownership_document["table_count"]):
        raise GrantPolicyError("inventory version or table count mismatch")
    seen = set()
    for row in rows:
        table = row.get("table")
        if not isinstance(table, str) or not IDENTIFIER_RE.fullmatch(table) or table in seen:
            raise GrantPolicyError("invalid or duplicate inventory table")
        seen.add(table)
        ownership = registry.table_owner(table)
        if (ownership is None or row.get("owner") != ownership.owner
                or row.get("runtime_domain") != ownership.runtime_domain
                or ownership.owner != ownership.runtime_domain):
            raise GrantPolicyError(f"inventory ownership mismatch: {table}")
    return DomainGrantPlan(tuple(AccountGrantPlan(
        domain, accounts[domain], tuple(sorted(row["table"] for row in rows
                                            if accounts[row["runtime_domain"]] == accounts[domain]))
    ) for domain in sorted(domains)))


def require_current_source_inventory(inventory: dict, registry=None) -> None:
    registry = registry or load_registry()
    violations, source_tables = audit_repository(REPO_ROOT, registry)
    rows = inventory.get("tables")
    if (not isinstance(rows, list) or
            any(not isinstance(row, dict) or not isinstance(row.get("table"), str) for row in rows) or
            set(source_tables) != {row["table"] for row in rows} or
            any(violation.category in {"unowned_table", "scan_error"} for violation in violations)):
        raise GrantPolicyError("current source table inventory or ownership drift")


def validate_grant_profile(environment: dict[str, str], *, database: str,
                           table_prefix: str, accounts: dict[str, str]) -> None:
    profile = environment.get("AI00_DEPLOY_PROFILE", "").strip()
    if (profile, table_prefix) not in (("test", "test_"), ("production", "pp_")) or (
            environment.get("TABLE_PREFIX", "").strip() != table_prefix):
        raise GrantPolicyError("grant profile and table prefix mismatch")
    try:
        validate_runtime_profile(profile, table_prefix, environment.get("PUBLIC_URL", ""))
    except ValueError as exc:
        raise GrantPolicyError("grant profile backend URL mismatch") from exc
    if environment.get("AI00_LOCAL_INTEGRATION_DB_URL", "").strip() or set(accounts) != set(URLS):
        raise GrantPolicyError("grant profile runtime account coverage mismatch")
    targets = set()
    for domain, variable in URLS.items():
        if "${" in environment.get(variable, ""):
            raise GrantPolicyError("grant profile has an interpolated runtime database URL")
        try:
            params = _params(environment.get(variable, ""))
        except (TypeError, ValueError) as exc:
            raise GrantPolicyError("grant profile has an invalid runtime database URL") from exc
        if params["user"] != accounts[domain]:
            raise GrantPolicyError("grant profile account identity mismatch")
        targets.add((params["host"], params["port"], params["database"]))
    if len(targets) != 1 or next(iter(targets))[2] != database:
        raise GrantPolicyError("grant profile database target mismatch")


def render_domain_grants(inventory: dict, *, database: str, table_prefix: str, host: str,
                         accounts: dict[str, str], include_revokes: bool = False) -> str:
    database = checked(database, IDENTIFIER_RE, "database")
    host = checked(host, HOST_RE, "host")
    if table_prefix not in ("test_", "pp_"):
        raise GrantPolicyError("table prefix must be test_ or pp_")
    plan = build_domain_grant_plan(accounts, inventory)
    tables = tuple(row["table"] for row in inventory["tables"])
    opposite_prefix = "pp_" if table_prefix == "test_" else "test_"
    lines = [
        "-- Review-only DML grant proposal; never execute without DBA approval.",
        f"-- database:{database} table-prefix:{table_prefix} runtime-domains:{len(plan.accounts)}",
        "-- DDL belongs to a separate migration identity; SHOW GRANTS and isolation probes remain required.",
    ]
    emitted = set()
    for account_plan in plan.accounts:
        if account_plan.account in emitted:
            continue
        emitted.add(account_plan.account)
        lines.extend(("", f"-- runtime-domain:{account_plan.label}"))
        lines.extend(_grant_line(database, table_prefix + table, account_plan.account, host)
                     for table in account_plan.tables)
        if include_revokes:
            forbidden = (table_prefix + table for table in tables
                         if table not in account_plan.tables)
            # Shared credentials do not establish isolation between environments.
            shared = sum(value == account_plan.account for value in accounts.values()) > 1
            forbidden = list(forbidden) + ([] if shared else [opposite_prefix + table for table in tables])
            lines.extend(f"REVOKE ALL PRIVILEGES ON `{database}`.`{table}` "
                         f"FROM '{account_plan.account}'@'{host}';" for table in sorted(forbidden))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "backend/governance/table_inventory.json")
    parser.add_argument("--database", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--table-prefix", required=True, choices=("test_", "pp_"))
    parser.add_argument("--host", default="%")
    parser.add_argument("--account", action="append", default=[], metavar="DOMAIN=USER")
    parser.add_argument("--account-group", action="append", default=[], metavar="GROUP=USER")
    parser.add_argument("--include-revokes", action="store_true")
    args = parser.parse_args()

    if args.account_group:
        raise GrantPolicyError("use --account DOMAIN=USER bindings; shared usernames are allowed")
    if args.env_file is None or not args.env_file.is_file():
        raise GrantPolicyError("explicit grant profile ENV_FILE is required")
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    registry = load_registry()
    runtime_domains = set(registry.product_domains)
    accounts = parse_accounts(args.account, runtime_domains)
    environment, _ = read_controlled_values(args.env_file)
    validate_grant_profile(environment, database=args.database, table_prefix=args.table_prefix,
                           accounts=accounts)
    build_domain_grant_plan(accounts, inventory, registry)
    require_current_source_inventory(inventory, registry)
    print(render_domain_grants(inventory, database=args.database, table_prefix=args.table_prefix,
                               host=args.host, accounts=accounts, include_revokes=args.include_revokes), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
