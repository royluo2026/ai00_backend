#!/usr/bin/env python3
"""Apply all Capability V2 domain migrations from a protected RC env file."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.rc_database_bootstrap import (
    BootstrapError,
    BootstrapRequest,
    parse_reuse_env,
)
from backend.scripts import run_domain_migrations


class RcDatabaseSetupError(RuntimeError):
    """Raised when protected env loading or a domain migration fails."""


_ERROR_MAP = {
    "reuse_env_keys_mismatch": "env_keys_mismatch",
    "reuse_env_duplicate_key": "env_duplicate_key",
    "reuse_env_value_invalid": "env_value_invalid",
    "reuse_env_record_invalid": "env_record_invalid",
    "reuse_env_key_invalid": "env_key_invalid",
    "reuse_env_unreadable": "env_unreadable",
}


def _records(path: Path) -> dict[str, str]:
    try:
        document = path.read_text(encoding="utf-8")
    except Exception:
        raise RcDatabaseSetupError("env_unreadable") from None
    if "\x00" in document:
        raise RcDatabaseSetupError("env_value_invalid")
    records: dict[str, str] = {}
    for line in document.splitlines():
        if not line or "=" not in line:
            raise RcDatabaseSetupError("env_record_invalid")
        name, value = line.split("=", 1)
        if name in records:
            raise RcDatabaseSetupError("env_duplicate_key")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise RcDatabaseSetupError("env_key_invalid")
        records[name] = value
    return records


def _load_database_environment(path: Path, root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    records = _records(path)
    required_metadata = {
        "AI00_RC_BOOTSTRAP_SCHEMA_VERSION",
        "AI00_RC_ENVIRONMENT_ID",
        "AI00_RC_TENANT",
        "AI00_RC_HOST",
        "AI00_RC_PORT",
    }
    if not required_metadata <= set(records):
        raise RcDatabaseSetupError("env_keys_mismatch")
    environment_id = records["AI00_RC_ENVIRONMENT_ID"].strip()
    normalized_environment = environment_id.casefold()
    if "prod" in normalized_environment or "production" in normalized_environment:
        raise RcDatabaseSetupError("production_environment_forbidden")
    if not any(marker in normalized_environment for marker in ("test", "rc")):
        raise RcDatabaseSetupError("environment_not_test_or_rc")
    tenant = records["AI00_RC_TENANT"].strip()
    normalized_tenant = tenant.casefold()
    if (
        normalized_tenant == "sys"
        or "prod" in normalized_tenant
        or not any(marker in normalized_tenant for marker in ("test", "rc"))
    ):
        raise RcDatabaseSetupError("tenant_not_test_or_rc")
    request = BootstrapRequest(
        environment_id=environment_id,
        host=records["AI00_RC_HOST"],
        url_tenant=tenant,
    )
    try:
        reuse = parse_reuse_env(path, root, request)
    except BootstrapError as exc:
        code = str(exc).split(":", 1)[0]
        raise RcDatabaseSetupError(_ERROR_MAP.get(code, code)) from None
    names = tuple(credential.env_name for credential in reuse.credentials)
    return {name: records[name] for name in names}, names


def _default_migrate(root: Path, domain_id: str, environment: Mapping[str, str]) -> int:
    return run_domain_migrations.main(
        ["--domain", domain_id, "--apply"],
        root=root,
        environ=environment,
    )


def _append_job_environment(
    path: Path,
    database_environment: Mapping[str, str],
    names: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for name in names:
            handle.write(f"{name}={database_environment[name]}\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = ROOT,
    environ: Mapping[str, str] = os.environ,
    migrate: Callable[[str, Mapping[str, str]], int] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--export-job-env", type=Path)
    args = parser.parse_args(argv)

    database_environment, names = _load_database_environment(args.env_file, root)
    process_environment = dict(environ)
    process_environment.update(database_environment)
    if args.export_job_env:
        _append_job_environment(args.export_job_env, database_environment, names)

    manifests = load_domain_manifests(
        root / "backend/capability_v2/official_domains.json"
    )
    runner = migrate or (
        lambda domain_id, environment: _default_migrate(
            root, domain_id, environment
        )
    )
    completed = 0
    for manifest in sorted(manifests.domains, key=lambda item: item.domain_id):
        try:
            result = runner(manifest.domain_id, process_environment)
        except Exception:
            raise RcDatabaseSetupError(
                f"migration_failed:{manifest.domain_id}"
            ) from None
        if result != 0:
            raise RcDatabaseSetupError(f"migration_failed:{manifest.domain_id}")
        completed += 1
        print(f"domain={manifest.domain_id} migration=passed")
    print(json.dumps({"domains": completed, "status": "migrated"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RcDatabaseSetupError as exc:
        print(f"RC database setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
