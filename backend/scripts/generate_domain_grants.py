#!/usr/bin/env python3
"""Generate (never execute) least-privilege OceanBase/MySQL grants."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.governance import load_registry

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_$.-]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9_$%.:-]+$")


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "backend/governance/table_inventory.json")
    parser.add_argument("--database", required=True)
    parser.add_argument("--host", default="%")
    parser.add_argument("--account", action="append", default=[], metavar="DOMAIN=USER")
    parser.add_argument("--include-revokes", action="store_true")
    args = parser.parse_args()

    database = checked(args.database, IDENTIFIER_RE, "database")
    host = checked(args.host, HOST_RE, "host")
    registry = load_registry()
    runtime_domains = set(registry.product_domains)
    accounts = parse_accounts(args.account, runtime_domains)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    if inventory.get("registry_version") != registry.version:
        raise ValueError("inventory registry version is stale")
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
