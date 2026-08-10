#!/usr/bin/env python3
"""Fail-closed deployment preflight for AI00 Plugin Platform acceptance."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from dataclasses import asdict, dataclass
from urllib.parse import urlparse
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
    return parsed.scheme in {"mysql", "mysql+pymysql"} and bool(parsed.hostname and parsed.username and parsed.path.strip("/"))


def evaluate(env: dict[str, str] | None = None) -> list[Check]:
    env = dict(os.environ if env is None else env)
    checks: list[Check] = []
    try:
        from backend.scripts.oceanbase_compatibility_audit import static_audit
        sql_issues = static_audit()
        detail = "compatible" if not sql_issues else f"{len(sql_issues)} issue(s)"
        checks.append(Check("OCEANBASE_STATIC_SQL", "pass" if not sql_issues else "fail", detail))
    except Exception as exc:
        checks.append(Check("OCEANBASE_STATIC_SQL", "fail", f"audit error: {type(exc).__name__}"))
    modules = ("pymysql", "dbutils", "cryptography", "requests", "client.ois_s3_client")
    for name in modules:
        ok = _module(name)
        checks.append(Check(f"module:{name}", "pass" if ok else "fail", "available" if ok else "not installed"))

    database_urls = (
        "AI00_DDL_DB_URL", "USERS_DB_URL", "AI00_CRAFT_DB_URL",
        "AI00_SIMULATION_DB_URL", "AI00_AGENT_DB_URL", "AI00_DEVICE_DB_URL",
        "AI00_PROJECT_MANAGEMENT_DB_URL", "AI00_KNOWLEDGE_DB_URL",
    )
    for name in database_urls:
        value = env.get(name, "").strip()
        checks.append(Check(name, "pass" if _mysql_url(value) else "fail", "configured mysql URL" if value and _mysql_url(value) else "missing or invalid mysql URL"))

    mount = env.get("AI00_PLUGIN_MOUNT_SECRET", "")
    checks.append(Check("AI00_PLUGIN_MOUNT_SECRET", "pass" if len(mount.encode()) >= 32 else "fail", "at least 32 bytes" if mount else "missing"))

    private_key = env.get("AI00_PLUGIN_PLATFORM_ED25519_PRIVATE_KEY", "").replace("\\n", "\n")
    key_ok, key_detail = False, "missing"
    if private_key and _module("cryptography"):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            key_ok = isinstance(serialization.load_pem_private_key(private_key.encode(), password=None), Ed25519PrivateKey)
            key_detail = "valid Ed25519 private key" if key_ok else "not an Ed25519 private key"
        except Exception:
            key_detail = "invalid private PEM"
    checks.append(Check("AI00_PLUGIN_PLATFORM_ED25519_PRIVATE_KEY", "pass" if key_ok else "fail", key_detail))

    ois_fields = ("OIS_IDENTIFY", "OIS_ENV", "OIS_OIS3_URL", "OIS_REGION", "OIS_LICLOUD_APPID", "OIS_IDAAS_URL", "OIS_IDAAS_CLIENT_ID", "OIS_IDAAS_CLIENT_SECRET", "OIS_IDAAS_SERVICE_ID")
    missing_ois = [name for name in ois_fields if not env.get(name, "").strip()]
    checks.append(Check("OIS_CONFIG", "pass" if not missing_ois else "fail", "complete" if not missing_ois else "missing: " + ", ".join(missing_ois)))

    api_url = env.get("AI00_ACCEPTANCE_API_URL", "").strip()
    token = env.get("AI00_ACCEPTANCE_ADMIN_TOKEN", "").strip()
    parsed = urlparse(api_url)
    checks.append(Check("AI00_ACCEPTANCE_API_URL", "pass" if parsed.scheme in {"http", "https"} and parsed.netloc else "fail", "configured" if api_url else "missing"))
    checks.append(Check("AI00_ACCEPTANCE_ADMIN_TOKEN", "pass" if token else "fail", "configured" if token else "missing"))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    checks = evaluate()
    if args.json:
        print(json.dumps({"ok": all(x.status == "pass" for x in checks), "checks": [asdict(x) for x in checks]}, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            print(f"[{item.status.upper():4}] {item.name}: {item.detail}")
        passed = sum(item.status == "pass" for item in checks)
        print(f"{passed}/{len(checks)} checks passed")
    return 0 if all(item.status == "pass" for item in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
