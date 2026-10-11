#!/usr/bin/env python3
"""Fail before restart when a deployment cannot serve its critical routes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import os
import re
import stat
import sys
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv.parser import parse_stream

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.table_prefix import REMOTE_BACKEND_ORIGINS, is_local_test_backend_url, validate_runtime_profile


REQUIRED_MODULES = ("cryptography", "dbutils", "pymysql", "multipart")
REQUIRED_DB_URLS = (
    "USERS_DB_URL",
    "AI00_CRAFT_DB_URL",
    "AI00_AGENT_DB_URL",
    "AI00_SIMULATION_DB_URL",
    "AI00_DEVICE_DB_URL",
    "AI00_PROJECT_MANAGEMENT_DB_URL",
    "AI00_KNOWLEDGE_DB_URL",
    "AI00_DIGITAL_MODEL_DB_URL",
    "AI00_INTEGRATION_DB_URL",
    "AI00_FACTORY_DB_URL",
    "AI00_ONTOLOGY_DB_URL",
)
PROCESS_BOUND_KEYS = (
    "AI00_DEPLOY_PROFILE", "TABLE_PREFIX", "PUBLIC_URL", "BACKEND_BASE_URL",
    "AI00_ALLOW_DATA_ENVIRONMENT_SWITCH", "AI00_DATA_ENVIRONMENT_STATE_FILE",
    "PORT", "DEBUG", "AI00_REQUIRE_MIGRATIONS", "CORS_ALLOW_ORIGINS",
    "FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_REDIRECT_URI", "JWT_SECRET",
    "AI00_DDL_DB_URL", "AI00_LOCAL_INTEGRATION_DB_URL",
    *REQUIRED_DB_URLS,
    *(key.replace("_DB_URL", "_DDL_DB_URL") for key in REQUIRED_DB_URLS if key != "USERS_DB_URL"),
)


def read_controlled_values(path: Path) -> tuple[dict[str, str], bytes]:
    try:
        selected = path.lstat()
        if not stat.S_ISREG(selected.st_mode) or selected.st_size > 65536:
            raise ValueError("controlled runtime env file is missing or invalid")
        identity = (selected.st_dev, selected.st_ino, selected.st_size, selected.st_mtime_ns)
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or
                    (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != identity):
                raise ValueError("controlled runtime env file changed while opening")
            document = stream.read(65537)
            after_read = os.fstat(stream.fileno())
        current = path.lstat()
        if (len(document) > 65536 or
                (after_read.st_dev, after_read.st_ino, after_read.st_size, after_read.st_mtime_ns) != identity or
                (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != identity):
            raise ValueError("controlled runtime env file changed while reading")
        source = document.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("controlled runtime env file is missing or invalid") from exc
    values: dict[str, str] = {}
    for binding in parse_stream(StringIO(source)):
        if binding.error or (binding.key is None and binding.original.string.strip().split("#", 1)[0].strip()):
            raise ValueError("controlled runtime env file contains an invalid record")
        if binding.key is None:
            continue
        if binding.key in values or binding.value is None:
            raise ValueError("controlled runtime env file contains a duplicate or empty assignment")
        values[binding.key] = binding.value.strip()
    return values, hashlib.sha256(document).digest()


def _runtime_account(value: str) -> dict[str, str | int]:
    from backend.scripts.verify_domain_db_isolation import _params

    parsed = urlsplit(value)
    if ("${" in unquote(value) or parsed.query or parsed.fragment or
            not parsed.path.startswith("/") or "/" in parsed.path[1:] or
            (parsed.port is not None and parsed.port < 1)):
        raise ValueError("runtime database URL must be explicit and unambiguous")
    return _params(value)


def validate_runtime_values(values: Mapping[str, str], *, allow_local: bool = False) -> list[str]:
    errors: list[str] = []
    profile = values.get("AI00_DEPLOY_PROFILE", "")
    prefix = values.get("TABLE_PREFIX", "")
    switch = values.get('AI00_ALLOW_DATA_ENVIRONMENT_SWITCH', '')
    if switch not in {'', '0', '1'}:
        errors.append('AI00_ALLOW_DATA_ENVIRONMENT_SWITCH must be 0 or 1')
    if profile == 'production' and switch == '1':
        state = values.get('AI00_DATA_ENVIRONMENT_STATE_FILE', '')
        if not state or not Path(state).is_absolute():
            errors.append('remote switching requires an absolute persistent state file')
        if values.get('AI00_WEB_WORKERS', '1') != '1':
            errors.append('remote switching requires one Gunicorn worker')
    local_runtime = (allow_local and not profile and not values.get("ENV_FILE")
                     and values.get("AI00_DEPLOYMENT_PROFILE") == "test-governance"
                     and is_local_test_backend_url(values.get("PUBLIC_URL", ""))
                     and (prefix == "test_" or (
                         values.get("AI00_ALLOW_DATA_ENVIRONMENT_SWITCH") == "1"
                         and values.get("AI00_DATA_ENVIRONMENT_STATE_FILE")
                         and prefix in {"pp_", ""})))
    if local_runtime:
        pass
    elif profile not in {"test", "production"}:
        errors.append("AI00_DEPLOY_PROFILE must explicitly select test or production")
    else:
        try:
            validate_runtime_profile(profile, prefix, values.get("PUBLIC_URL", ""))
        except ValueError:
            errors.append("AI00_DEPLOY_PROFILE, TABLE_PREFIX and PUBLIC_URL mismatch")
    if values.get("AI00_LOCAL_INTEGRATION_DB_URL", ""):
        errors.append("legacy local integration database account is not an approved runtime domain")
    from backend.scripts.verify_domain_db_isolation import URLS
    if set(URLS.values()) != set(REQUIRED_DB_URLS):
        errors.append("runtime account coverage does not match isolation probe domains")
    accounts = {}
    for name in REQUIRED_DB_URLS:
        try:
            accounts[name] = _runtime_account(values.get(name, ""))
        except (TypeError, ValueError):
            errors.append(f"{name} is missing or is not an explicit mysql URL")
    if len(accounts) == len(REQUIRED_DB_URLS):
        if len({(account["host"], account["port"], account["database"])
                for account in accounts.values()}) != 1:
            errors.append("runtime domains must target the same physical database")
    return errors


def _valid_production_cors_origin(value: str) -> bool:
    if value == "app://root":
        return True
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    host = parsed.hostname
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or
            (port is not None and port < 1)):
        return False
    try:
        address = ipaddress.ip_address(host)
        return not (address.is_loopback or address.is_unspecified)
    except ValueError:
        labels = host.split(".")
        return bool(len(labels) >= 2 and len(host) <= 253 and
                    not host.endswith(".localhost") and not re.fullmatch(r"[0-9.]+", host) and
                    all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                        for label in labels))


def validate_deployment_values(values: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    profile = values.get("AI00_DEPLOY_PROFILE", "")
    if profile not in {"test", "production"}:
        return errors
    for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "JWT_SECRET"):
        value = values.get(name, "")
        if not value or value.startswith("REQUIRED_"):
            errors.append(f"{profile} {name} is not configured")
    callback = values.get("FEISHU_REDIRECT_URI", "")
    if profile == "test":
        if not is_local_test_backend_url(values.get("PUBLIC_URL", "")):
            errors.append("test PUBLIC_URL must point to loopback or this PC on port 8080")
        if values.get("PORT") != "8080":
            errors.append("test profile requires PORT=8080")
        if values.get("BACKEND_BASE_URL", "") not in {"", "http://127.0.0.1:8080"}:
            errors.append("test BACKEND_BASE_URL must point to the local backend")
        if callback != "http://127.0.0.1:8080/auth/feishu/callback":
            errors.append("test Feishu redirect URI mismatch")
    else:
        if values.get("AI00_REQUIRE_MIGRATIONS") != "1":
            errors.append("production requires AI00_REQUIRE_MIGRATIONS=1")
        if values.get("DEBUG", "").lower() != "false":
            errors.append("production requires DEBUG=false")
        port = values.get("PORT", "")
        valid_port = bool(re.fullmatch(r"[0-9]{1,5}", port)) and 1 <= int(port) <= 65535
        if not valid_port:
            errors.append("production PORT must be a valid explicit port")
        public_origin = values.get('PUBLIC_URL', '').rstrip('/')
        allowed_self_calls = {public_origin} if public_origin in REMOTE_BACKEND_ORIGINS else set()
        if valid_port:
            allowed_self_calls.add(f"http://127.0.0.1:{port}")
        if values.get("BACKEND_BASE_URL", "") not in allowed_self_calls:
            errors.append("production BACKEND_BASE_URL must use its own loopback port or production backend origin")
        if public_origin not in REMOTE_BACKEND_ORIGINS or callback != public_origin + '/auth/feishu/callback':
            errors.append("production Feishu redirect URI mismatch")
        origins = values.get("CORS_ALLOW_ORIGINS", "")
        if not origins or not all(_valid_production_cors_origin(origin.strip())
                                  for origin in origins.split(",")):
            errors.append("production CORS origins must be explicit HTTPS/desktop origins")
    return errors


def evaluate(env_file: Path, process_env: Mapping[str, str] | None = None) -> list[str]:
    try:
        values, _ = read_controlled_values(env_file)
    except ValueError as exc:
        return [str(exc)]
    if process_env is not None and any(
        process_env.get(key, "").strip() != values.get(key, "")
        for key in PROCESS_BOUND_KEYS
    ):
        return ["managed runtime process configuration differs from ENV_FILE"]
    errors = [f"required Python module is not installed: {name}" for name in REQUIRED_MODULES
              if importlib.util.find_spec(name) is None]
    return errors + validate_runtime_values(values) + validate_deployment_values(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    errors = evaluate(args.env_file)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 2
    print("Runtime preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
