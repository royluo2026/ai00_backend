#!/usr/bin/env python3
"""Fail-closed preflight for staged legacy Knowledge Markdown migration acceptance."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WRITE_ACK = "I_UNDERSTAND_SOURCE_IS_RETAINED"
_NON_PROD = {"test", "ontest", "staging"}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def _module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _mysql_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme in {"mysql", "mysql+pymysql"}
        and bool(parsed.hostname and parsed.username and parsed.path.strip("/"))
    )


def evaluate(
    env: dict[str, str] | None = None,
    module_probe: Callable[[str], bool] = _module,
) -> list[Check]:
    env = dict(os.environ if env is None else env)
    checks: list[Check] = []

    from backend.scripts.oceanbase_compatibility_audit import static_audit
    issues = static_audit()
    checks.append(Check(
        "OCEANBASE_STATIC_SQL",
        "pass" if not issues else "fail",
        "compatible" if not issues else f"{len(issues)} issue(s)",
    ))

    required_migrations = (
        "202608040003_knowledge_markdown_revisions.sql",
        "202608040004_knowledge_legacy_migration_runs.sql",
    )
    migration_root = REPO_ROOT / "backend/db/migrations"
    missing_migrations = [name for name in required_migrations if not (migration_root / name).is_file()]
    checks.append(Check(
        "KNOWLEDGE_MIGRATIONS",
        "pass" if not missing_migrations else "fail",
        "present" if not missing_migrations else "missing: " + ", ".join(missing_migrations),
    ))

    from backend.capabilities.registry_next import capability_registry
    required_capabilities = (
        "knowledge.document.get",
        "knowledge.document.revisions",
        "knowledge.migration.status",
    )
    missing_capabilities = []
    for capability_id in required_capabilities:
        try:
            capability_registry.get(capability_id)
        except KeyError:
            missing_capabilities.append(capability_id)
    checks.append(Check(
        "KNOWLEDGE_CAPABILITIES",
        "pass" if not missing_capabilities else "fail",
        "registered" if not missing_capabilities else "missing: " + ", ".join(missing_capabilities),
    ))

    for module_name in ("pymysql", "dbutils", "client.ois_s3_client"):
        ok = module_probe(module_name)
        checks.append(Check(
            f"module:{module_name}", "pass" if ok else "fail",
            "available" if ok else "not installed",
        ))

    for name in ("AI00_DDL_DB_URL", "USERS_DB_URL"):
        value = env.get(name, "").strip()
        ok = _mysql_url(value)
        checks.append(Check(
            name, "pass" if ok else "fail",
            "configured mysql URL" if ok else "missing or invalid mysql URL",
        ))

    ois_fields = (
        "OIS_IDENTIFY", "OIS_ENV", "OIS_OIS3_URL", "OIS_REGION", "OIS_LICLOUD_APPID",
        "OIS_IDAAS_URL", "OIS_IDAAS_CLIENT_ID", "OIS_IDAAS_CLIENT_SECRET",
        "OIS_IDAAS_SERVICE_ID",
    )
    missing_ois = [name for name in ois_fields if not env.get(name, "").strip()]
    checks.append(Check(
        "OIS_CONFIG", "pass" if not missing_ois else "fail",
        "complete" if not missing_ois else "missing: " + ", ".join(missing_ois),
    ))

    for name in (
        "AI00_KNOWLEDGE_ACCEPTANCE_TENANT_GID",
        "AI00_KNOWLEDGE_ACCEPTANCE_SPACE_GID",
        "AI00_KNOWLEDGE_ACCEPTANCE_ACTOR_GID",
    ):
        value = env.get(name, "").strip()
        ok = bool(_SAFE_ID.fullmatch(value))
        checks.append(Check(name, "pass" if ok else "fail", "valid identifier" if ok else "missing or invalid identifier"))

    deployment = env.get("AI00_DEPLOYMENT_ENV", "").strip().lower()
    checks.append(Check(
        "NON_PRODUCTION_ENV",
        "pass" if deployment in _NON_PROD else "fail",
        f"accepted non-production environment: {deployment}" if deployment in _NON_PROD else "must be test, ontest, or staging",
    ))
    acknowledged = env.get("AI00_KNOWLEDGE_ACCEPTANCE_WRITE_TOKEN", "") == _WRITE_ACK
    checks.append(Check(
        "WRITE_ACKNOWLEDGEMENT",
        "pass" if acknowledged else "fail",
        "explicit source-retention acknowledgement present" if acknowledged else "missing explicit write acknowledgement",
    ))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    checks = evaluate()
    ok = all(item.status == "pass" for item in checks)
    if args.json:
        print(json.dumps({"ok": ok, "checks": [asdict(item) for item in checks]}, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            print(f"[{item.status.upper():4}] {item.name}: {item.detail}")
        print(f"{sum(item.status == 'pass' for item in checks)}/{len(checks)} checks passed")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
