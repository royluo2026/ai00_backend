#!/usr/bin/env python3
"""Deployment-only OceanBase migration entrypoint."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.oceanbase_compat import verify_live_server
from backend.db.prefixed_cursor import wrap_connection
from backend.db.table_prefix import configure_table_prefix, validate_runtime_profile
from backend.db.versioned_migrations import apply_bootstrap_schema, apply_migrations
from backend.scripts.runtime_preflight import read_controlled_values


def main() -> int:
    env_file = os.environ.get("ENV_FILE", "").strip()
    target = os.environ
    if env_file:
        try:
            target, _ = read_controlled_values(Path(env_file))
        except ValueError as error:
            raise SystemExit(str(error)) from error
    raw = str(target.get("AI00_DDL_DB_URL") or "")
    if not raw:
        raise SystemExit("AI00_DDL_DB_URL is required; application runtime credentials are refused")
    parsed = urlparse(raw)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise SystemExit("AI00_DDL_DB_URL must be a mysql:// URL with an explicit database")
    import pymysql

    prefix = str(target.get("TABLE_PREFIX") or "")
    profile = str(target.get("AI00_DEPLOY_PROFILE") or "")
    if env_file and not profile:
        raise SystemExit("managed_deployment_requires_explicit_profile")
    if prefix not in {"test_", "pp_"}:
        raise SystemExit("migration TABLE_PREFIX must be test_ or pp_")
    if prefix == "pp_" and not env_file:
        raise SystemExit("pp_ migration requires ENV_FILE")
    try:
        validate_runtime_profile(profile, prefix, str(target.get("PUBLIC_URL") or ""))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    configure_table_prefix(prefix)
    conn = wrap_connection(pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    ))
    try:
        profile = verify_live_server(conn)
        print(f"OceanBase compatibility verified: {profile['version']} ({profile['compatibility_mode']})")
        bootstrap_path = REPO_ROOT / "backend/db/mysql_schema.sql"
        bootstrapped = apply_bootstrap_schema(conn, bootstrap_path)
        print("baseline schema initialized" if bootstrapped else "baseline schema already present")
        applied = apply_migrations(conn)
        print(f"applied {len(applied)} migration(s): {', '.join(applied) or 'none'}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
