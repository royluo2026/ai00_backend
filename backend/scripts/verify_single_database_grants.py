#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from backend.governance import load_registry
from backend.scripts.runtime_preflight import read_controlled_values
from backend.scripts.generate_domain_grants import build_domain_grant_plan, checked, parse_accounts, require_current_source_inventory, validate_grant_profile, IDENTIFIER_RE, HOST_RE

DML = {"SELECT", "INSERT", "UPDATE", "DELETE"}
GRANT_RE = re.compile(r"^GRANT\s+(.+?)\s+ON\s+(`?[^`.\s]+`?|\*)\s*\.\s*(`?[^`\s]+`?|\*)\s+TO\s+'([^']+)'@'([^']+)'(?:\s|$)", re.I)


@dataclass(frozen=True)
class GrantVerification:
    account_label: str
    expected_table_count: int
    actual_table_count: int
    missing_tables: tuple[str, ...]
    extra_tables: tuple[str, ...]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing_tables and not self.extra_tables and not self.failures

    def to_dict(self) -> dict[str, object]:
        return {
            "account_label": self.account_label, "passed": self.passed,
            "expected_table_count": self.expected_table_count,
            "actual_table_count": self.actual_table_count,
            "missing_tables": list(self.missing_tables), "extra_tables": list(self.extra_tables),
            "failures": list(self.failures),
        }


def verify_grant_rows(rows: list[str], *, expected_tables: tuple[str, ...],
                      account_label: str, database: str = "ai00_test",
                      account: str | None = None, host: str | None = None) -> GrantVerification:
    actual, failures = set(), set()
    for raw in rows:
        grant = str(raw).strip().rstrip(";")
        if re.search(r"\bWITH\s+GRANT\s+OPTION\b", grant, re.I): failures.add("grant_option_present")
        match = GRANT_RE.match(grant)
        if not match:
            failures.add("unparsed_grant_row"); continue
        privileges_text, scope_db, scope_table, row_account, row_host = match.groups()
        if account is not None and (row_account != account or row_host != host):
            failures.add("account_identity_mismatch")
        privileges = {item.strip().upper() for item in privileges_text.split(",")}
        scope_db, scope_table = scope_db.replace("`", ""), scope_table.replace("`", "")
        if privileges == {"USAGE"} and scope_db == "*" and scope_table == "*": continue
        if "ALL PRIVILEGES" in privileges or "ALL" in privileges: failures.add("all_privileges_present")
        if privileges - DML: failures.add("ddl_privilege_present")
        if scope_db == "*" or scope_table == "*": failures.add("wildcard_scope_present"); continue
        if scope_db != database: failures.add("foreign_database_scope"); continue
        actual.add(scope_table)
        if privileges != DML: failures.add("dml_privilege_mismatch")
    expected = set(expected_tables)
    return GrantVerification(account_label, len(expected), len(actual),
        tuple(sorted(expected - actual)), tuple(sorted(actual - expected)), tuple(sorted(failures)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify captured SHOW GRANTS without credentials")
    parser.add_argument("--input", type=Path, help="JSON object mapping account labels to SHOW GRANTS rows; default stdin")
    parser.add_argument("--inventory", type=Path, default=ROOT / "backend/governance/table_inventory.json")
    parser.add_argument("--database", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--table-prefix", required=True, choices=("test_", "pp_"))
    parser.add_argument("--host", default="%")
    parser.add_argument("--account", action="append", default=[], metavar="DOMAIN=USER")
    args = parser.parse_args()
    if args.env_file is None or not args.env_file.is_file():
        raise ValueError("explicit grant profile ENV_FILE is required")
    database = checked(args.database, IDENTIFIER_RE, "database")
    host = checked(args.host, HOST_RE, "host")
    document = json.loads(args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read())
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    registry = load_registry()
    accounts = parse_accounts(args.account, set(registry.product_domains))
    environment, _ = read_controlled_values(args.env_file)
    validate_grant_profile(environment, database=database, table_prefix=args.table_prefix,
                           accounts=accounts)
    plan = build_domain_grant_plan(accounts, inventory, registry)
    require_current_source_inventory(inventory, registry)
    if not isinstance(document, dict) or set(document) != set(accounts):
        raise ValueError("grant input must contain exactly eleven runtime domain labels")
    if any(not isinstance(rows, list) or any(not isinstance(row, str) for row in rows)
           for rows in document.values()):
        raise ValueError("grant rows must be arrays of strings")
    results = [verify_grant_rows(document[item.label],
                                 expected_tables=tuple(args.table_prefix + table for table in item.tables),
                                 account_label=item.label, database=database,
                                 account=item.account, host=host) for item in plan.accounts]
    print(json.dumps({"passed": all(item.passed for item in results),
                      "accounts": [item.to_dict() for item in results]}, sort_keys=True))
    return 0 if all(item.passed for item in results) else 1


if __name__ == "__main__": raise SystemExit(main())
