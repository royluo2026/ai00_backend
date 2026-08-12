#!/usr/bin/env python3
"""Safely bootstrap isolated Capability V2 RC domain databases."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping, Sequence
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.rc_database_bootstrap import (
    BootstrapError,
    BootstrapRequest,
    build_bootstrap_plan,
    execute_bootstrap_plan,
    parse_reuse_env,
    render_bootstrap_env,
    validate_bootstrap_target,
    verify_reuse_environment,
)


def _parse_admin_url(value: str) -> dict[str, object]:
    try:
        parsed = urlparse(value)
        port = parsed.port or 2881
    except (TypeError, ValueError):
        raise BootstrapError("admin_url_invalid") from None
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = unquote(parsed.path.removeprefix("/"))
    if database != "oceanbase":
        raise BootstrapError("admin_url_database_invalid")
    if (
        parsed.scheme not in {"mysql", "mysql+pymysql"}
        or not parsed.hostname
        or not username
        or not password
        or parsed.params
        or parsed.query
        or parsed.fragment
        or username.count("@") != 1
    ):
        raise BootstrapError("admin_url_invalid")
    local_user, tenant = username.rsplit("@", 1)
    if not local_user or not tenant:
        raise BootstrapError("admin_url_invalid")
    return {
        "host": parsed.hostname,
        "port": port,
        "username": username,
        "password": password,
        "database": database,
        "tenant": tenant,
    }


def _default_connect(**kwargs):
    import pymysql

    return pymysql.connect(**kwargs)


def _protect_file(
    path: Path,
    *,
    platform_name: str | None = None,
    username: str | None = None,
    run: Callable[..., object] | None = None,
) -> None:
    active_platform = platform_name or os.name
    active_username = username or getpass.getuser()
    execute = run or subprocess.run
    if active_platform == "nt":
        completed = execute(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{active_username}:F",
                "SYSTEM:F",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise BootstrapError("env_file_protection_failed")
    else:
        path.chmod(0o600)


def _write_protected(
    path: Path,
    content: str,
    protect_file: Callable[[Path], None],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)
    try:
        protect_file(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise BootstrapError("env_file_protection_failed") from None


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    connect: Callable[..., object] = _default_connect,
    protect_file: Callable[[Path], None] = _protect_file,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url-env", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--output-env", type=Path, required=True)
    parser.add_argument("--allow-host")
    parser.add_argument("--reuse-env", type=Path)
    args = parser.parse_args(argv)

    admin_url = str(environ.get(args.admin_url_env, "")).strip()
    if not admin_url:
        raise BootstrapError("admin_url_env_missing")
    parsed = _parse_admin_url(admin_url)
    request = BootstrapRequest(
        environment_id=args.environment_id,
        host=str(parsed["host"]),
        allow_host=args.allow_host,
        url_tenant=str(parsed["tenant"]),
    )
    connection = connect(
        host=parsed["host"],
        port=parsed["port"],
        user=parsed["username"],
        password=parsed["password"],
        database=parsed["database"],
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        tenant = validate_bootstrap_target(connection, request)
        if args.reuse_env:
            reuse = parse_reuse_env(args.reuse_env, ROOT, request)
            if reuse.tenant != tenant or reuse.port != int(parsed["port"]):
                raise BootstrapError("reuse_target_mismatch")
            verify_reuse_environment(reuse, connect=connect)
            output_document = reuse.document
            status = "reused"
            domain_count = len(reuse.credentials) // 2
        else:
            plan = build_bootstrap_plan(
                ROOT,
                request,
                tenant=tenant,
                port=int(parsed["port"]),
            )
            execute_bootstrap_plan(connection, plan)
            output_document = render_bootstrap_env(plan)
            status = "created"
            domain_count = len(plan.domains)
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()
    _write_protected(args.output_env, output_document, protect_file)
    print(
        json.dumps(
            {
                "databases": domain_count,
                "environment_id": request.environment_id,
                "principals": domain_count * 2,
                "status": status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BootstrapError as exc:
        print(f"RC database bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
