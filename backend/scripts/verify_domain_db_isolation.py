#!/usr/bin/env python3
"""Verify OceanBase runtime accounts can access only tables owned by their domain."""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
IDENTIFIER = re.compile(r"^[A-Za-z0-9_$]+$")
URLS = {
    "base": "USERS_DB_URL",
    "craft": "AI00_CRAFT_DB_URL",
    "simulation": "AI00_SIMULATION_DB_URL",
    "agent": "AI00_AGENT_DB_URL",
    "device": "AI00_DEVICE_DB_URL",
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
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("must be a mysql URL with an explicit database")
    return {"host":parsed.hostname, "port":parsed.port or 3306, "user":unquote(parsed.username or ""), "password":unquote(parsed.password or ""), "database":parsed.path.strip("/")}


def _code(exc: Exception) -> int | None:
    try: return int(exc.args[0])
    except (IndexError, TypeError, ValueError): return None


def verify(inventory_path: Path, *, verify_ddl_denied: bool = False, env: dict[str, str] | None = None) -> list[Result]:
    env = dict(os.environ if env is None else env)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    tables = inventory.get("tables", [])
    if not tables or any(not IDENTIFIER.fullmatch(str(item.get("table", ""))) for item in tables):
        raise ValueError("inventory is empty or contains unsafe table names")
    results: list[Result] = []
    if not any(env.get(variable, "").strip() for variable in URLS.values()):
        return [Result(domain, "connection", variable, False, "missing database URL") for domain, variable in URLS.items()]
    import pymysql
    for domain, variable in URLS.items():
        raw = env.get(variable, "").strip()
        if not raw:
            results.append(Result(domain, "connection", variable, False, "missing database URL")); continue
        try:
            params = _params(raw)
            connection = pymysql.connect(**params, charset="utf8mb4", autocommit=False)
        except Exception as exc:
            results.append(Result(domain, "connection", variable, False, f"connection failed ({type(exc).__name__})")); continue
        results.append(Result(domain, "connection", variable, True, "connected"))
        try:
            with connection.cursor() as cursor:
                for item in tables:
                    table, owner = item["table"], item["runtime_domain"]
                    try:
                        cursor.execute(f"SELECT 1 FROM `{params['database']}`.`{table}` WHERE 1=0")
                        allowed = True; code = None
                    except Exception as exc:
                        allowed = False; code = _code(exc)
                    expected = owner == domain
                    ok = allowed if expected else (not allowed and code in DENIED_CODES)
                    detail = "allowed" if allowed else f"denied/error code {code}"
                    results.append(Result(domain, "owned-allow" if expected else "foreign-deny", table, ok, detail))
                if verify_ddl_denied:
                    probe = f"ai00_permission_probe_{domain}"
                    try:
                        cursor.execute(f"CREATE TABLE `{params['database']}`.`{probe}` (id INT PRIMARY KEY)")
                        connection.commit()
                        try:
                            cursor.execute(f"DROP TABLE `{params['database']}`.`{probe}`")
                            connection.commit()
                        finally:
                            results.append(Result(domain, "ddl-deny", probe, False, "CREATE unexpectedly succeeded; probe was removed"))
                    except Exception as exc:
                        connection.rollback()
                        code = _code(exc)
                        results.append(Result(domain, "ddl-deny", probe, code in DENIED_CODES, f"denied/error code {code}"))
        finally:
            connection.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "backend/governance/table_inventory.json")
    parser.add_argument("--verify-ddl-denied", action="store_true", help="Attempt a uniquely named probe CREATE and remove it if permissions are unexpectedly broad.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = verify(args.inventory, verify_ddl_denied=args.verify_ddl_denied)
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