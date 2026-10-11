#!/usr/bin/env python3
"""Verify OceanBase runtime accounts can access only tables owned by their domain."""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.table_prefix import validate_runtime_profile
from backend.scripts.runtime_preflight import REQUIRED_DB_URLS, read_controlled_values
IDENTIFIER = re.compile(r"^[A-Za-z0-9_$]+$")
URLS = {
    "base": "USERS_DB_URL",
    "agent": "AI00_AGENT_DB_URL",
    "craft": "AI00_CRAFT_DB_URL",
    "digital_model": "AI00_DIGITAL_MODEL_DB_URL",
    "project_management": "AI00_PROJECT_MANAGEMENT_DB_URL",
    "simulation": "AI00_SIMULATION_DB_URL",
    "ontology": "AI00_ONTOLOGY_DB_URL",
    "knowledge": "AI00_KNOWLEDGE_DB_URL",
    "device": "AI00_DEVICE_DB_URL",
    "factory": "AI00_FACTORY_DB_URL",
    "integration": "AI00_INTEGRATION_DB_URL",
}
DENIED_CODES = {1044, 1045, 1142, 1143, 1227}


@dataclass(frozen=True)
class Result:
    domain: str
    check: str
    target: str
    ok: bool
    detail: str


def _params(raw: str) -> dict:
    parsed = urlparse(raw)
    if (parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname
            or not parsed.username or not parsed.password or not parsed.path.strip("/")):
        raise ValueError("must be a mysql URL with an explicit database")
    database = parsed.path.strip("/")
    if not IDENTIFIER.fullmatch(database):
        raise ValueError("database name is not a safe SQL identifier")
    return {"host":parsed.hostname, "port":parsed.port or 3306, "user":unquote(parsed.username or ""), "password":unquote(parsed.password or ""), "database":database}


def _code(exc: Exception) -> int | None:
    try: return int(exc.args[0])
    except (IndexError, TypeError, ValueError): return None


def _probe_ddl_denial(cursor, connection, *, domain: str, database: str) -> Result:
    probe = f"ai00_permission_probe_{domain}_{secrets.token_hex(8)}"
    target = f"{database}.{probe}"
    try:
        cursor.execute(f"CREATE TABLE `{database}`.`{probe}` (id INT PRIMARY KEY)")
    except Exception as exc:
        connection.rollback()
        code = _code(exc)
        return Result(domain, "ddl-deny", target, code in DENIED_CODES, f"denied/error code {code}")
    try:
        connection.commit()
    except Exception:
        connection.rollback()
    try:
        cursor.execute(f"DROP TABLE `{database}`.`{probe}`")
        connection.commit()
    except Exception as exc:
        connection.rollback()
        return Result(domain, "ddl-deny", target, False,
                      f"CREATE unexpectedly succeeded; cleanup unverified ({type(exc).__name__})")
    return Result(domain, "ddl-deny", target, False, "CREATE unexpectedly succeeded; probe removed")


def _probe_write_denial(cursor, connection, *, domain: str, database: str,
                        table: str, check: str) -> Result:
    target = f"{database}.{table}"
    try:
        cursor.execute(f"DELETE FROM `{database}`.`{table}` WHERE 1=0")
        allowed, code = True, None
    except Exception as exc:
        allowed, code = False, _code(exc)
    try:
        connection.rollback()
    except Exception as exc:
        return Result(domain, "write-rollback-failed", target, False,
                      f"rollback unverified ({type(exc).__name__})")
    return Result(domain, check, target, not allowed and code in DENIED_CODES,
                  "allowed" if allowed else f"denied/error code {code}")


def verify(inventory_path: Path, *, verify_ddl_denied: bool = False,
           verify_write_denied: bool = False, env: dict[str, str] | None = None) -> list[Result]:
    if env is None:
        raise ValueError("isolation verification requires an explicit environment file")
    env = dict(env)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    tables = inventory.get("tables", [])
    if not tables or any(not IDENTIFIER.fullmatch(str(item.get("table", ""))) for item in tables):
        raise ValueError("inventory is empty or contains unsafe table names")
    if (inventory.get("table_count") != len(tables) or len({item["table"] for item in tables}) != len(tables)
            or {item.get("runtime_domain") for item in tables} != set(URLS)
            or any(item.get("owner") != item.get("runtime_domain") for item in tables)):
        raise ValueError("inventory count, unique tables or runtime domain coverage mismatch")
    results: list[Result] = []
    configured_variables = list(URLS.values())
    if not any(env.get(variable, "").strip() for variable in configured_variables):
        return [Result(domain, "connection", variable, False, "missing database URL") for domain, variable in URLS.items()]
    if set(URLS.values()) != set(REQUIRED_DB_URLS):
        return [Result("unmapped", "account-coverage-unverified", variable, False,
                       "runtime account has no approved domain isolation probe")
                for variable in sorted(set(REQUIRED_DB_URLS) - set(URLS.values()))]
    prefix = env.get("TABLE_PREFIX", "").strip()
    profile = env.get("AI00_DEPLOY_PROFILE", "").strip()
    if prefix not in {"test_", "pp_"} or profile not in {"test", "production"}:
        raise ValueError("isolation verification requires explicit profile and TABLE_PREFIX")
    validate_runtime_profile(profile, prefix, env.get("PUBLIC_URL", ""))
    if env.get("AI00_LOCAL_INTEGRATION_DB_URL", "").strip():
        return [Result("local_integration", "account-coverage-unverified", "AI00_LOCAL_INTEGRATION_DB_URL", False,
                       "legacy account has no approved runtime table mapping")]
    missing = [(domain, variable) for domain, variable in URLS.items() if not env.get(variable, "").strip()]
    if missing:
        return [Result(domain, "connection", variable, False, "missing database URL") for domain, variable in missing]
    try:
        params_by_domain = {domain: _params(env[variable].strip()) for domain, variable in URLS.items()}
    except ValueError as exc:
        raise ValueError("invalid runtime database URL for isolation verification") from exc
    targets = {(params["host"], params["port"], params["database"]) for params in params_by_domain.values()}
    if len(targets) != 1:
        return [Result("unmapped", "target-mismatch", "runtime domain URLs", False,
                       "runtime accounts must target the same configured database")]
    import pymysql
    for domain, variable in URLS.items():
        try:
            params = params_by_domain[domain]
            shared_domains = {owner for owner, other in params_by_domain.items() if other['user'] == params['user']}
            shared = len(shared_domains) > 1
            connection = pymysql.connect(**params, charset="utf8mb4", autocommit=False)
        except Exception as exc:
            results.append(Result(domain, "connection", variable, False, f"connection failed ({type(exc).__name__})")); continue
        results.append(Result(domain, "connection", variable, True, "connected"))
        try:
            with connection.cursor() as cursor:
                for item in tables:
                    table, owner = prefix + item["table"], item["runtime_domain"]
                    try:
                        cursor.execute(f"SELECT 1 FROM `{params['database']}`.`{table}` WHERE 1=0")
                        allowed = True; code = None
                    except Exception as exc:
                        allowed = False; code = _code(exc)
                    expected = owner in shared_domains
                    ok = allowed if expected else (not allowed and code in DENIED_CODES)
                    detail = "allowed" if allowed else f"denied/error code {code}"
                    check = "shared-table-allow" if shared and expected else "owned-allow" if expected else "foreign-deny"
                    results.append(Result(domain, check, table, ok, detail))
                    other_table = ("pp_" if prefix == "test_" else "test_") + item["table"]
                    try:
                        cursor.execute(f"SELECT 1 FROM `{params['database']}`.`{other_table}` WHERE 1=0")
                        other_allowed = True; other_code = None
                    except Exception as exc:
                        other_allowed = False; other_code = _code(exc)
                    other_ok = (other_allowed or other_code in DENIED_CODES) if shared else (not other_allowed and other_code in DENIED_CODES)
                    other_detail = "allowed" if other_allowed else f"denied/error code {other_code}"
                    results.append(Result(domain, "cross-prefix-observation" if shared else "cross-prefix-deny", other_table, other_ok, other_detail))
                    if verify_write_denied:
                        write_targets = [] if shared else [(other_table, "cross-prefix-write-deny")]
                        if not expected:
                            write_targets.append((table, "foreign-write-deny"))
                        for write_table, check in write_targets:
                            result = _probe_write_denial(cursor, connection, domain=domain,
                                                         database=params["database"],
                                                         table=write_table, check=check)
                            results.append(result)
                            if result.check == "write-rollback-failed":
                                return results
                if verify_ddl_denied:
                    results.append(_probe_ddl_denial(cursor, connection, domain=domain,
                                                     database=params["database"]))
        finally:
            connection.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "backend/governance/table_inventory.json")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--verify-ddl-denied", action="store_true", help="Attempt a uniquely named probe CREATE and remove it if permissions are unexpectedly broad.")
    parser.add_argument("--verify-write-denied", action="store_true", help="Attempt DELETE WHERE 1=0 on foreign and opposite-prefix tables; requires separate DBA approval on a real database.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        environment, _ = read_controlled_values(args.env_file)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    results = verify(args.inventory, verify_ddl_denied=args.verify_ddl_denied,
                     verify_write_denied=args.verify_write_denied, env=environment)
    failures = [item for item in results if not item.ok]
    if args.json:
        print(json.dumps({"ok":not failures,"checks":len(results),"failures":[asdict(item) for item in failures],"results":[asdict(item) for item in results]}, ensure_ascii=False, indent=2))
    else:
        by_domain = {domain: [item for item in results if item.domain == domain] for domain in URLS}
        for domain, items in by_domain.items():
            failed = sum(not item.ok for item in items)
            print(f"{domain}: {len(items)-failed}/{len(items)} passed")
            for item in items:
                if not item.ok: print(f"  FAIL {item.check} {item.target}: {item.detail}")
        print(f"total: {len(results)-len(failures)}/{len(results)} passed")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
