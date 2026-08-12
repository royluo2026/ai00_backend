#!/usr/bin/env python3
"""Validate or apply migrations for exactly one domain database."""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.domain_database import (
    connect_domain_database,
    load_domain_database_config,
    load_domain_database_url,
)
from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.domain_migrations import (
    apply_domain_migrations,
    discover_domain_migrations,
)
from backend.db.oceanbase_compat import verify_live_server


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = REPOSITORY_ROOT,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    environment = os.environ if environ is None else environ
    manifests = load_domain_manifests(root / "backend/capability_v2/official_domains.json")
    try:
        manifest = manifests.require(args.domain)
    except KeyError:
        parser.error(f"unknown domain: {args.domain}")
    migrations = discover_domain_migrations(root, manifest)

    runtime_env = manifest.database.runtime_url_env
    ddl_env = manifest.database.ddl_url_env
    if args.check:
        if environment.get(runtime_env) and environment.get(ddl_env):
            load_domain_database_config(manifest, environment)
        elif environment.get(runtime_env):
            load_domain_database_url(manifest, environment, role="runtime")
        elif environment.get(ddl_env):
            load_domain_database_url(manifest, environment, role="ddl")
        print(f"domain={manifest.domain_id} migrations={len(migrations)} mode=check")
        return 0

    ddl_url = load_domain_database_url(manifest, environment, role="ddl")
    connection = connect_domain_database(ddl_url)
    try:
        profile = verify_live_server(connection)
        applied = apply_domain_migrations(connection, manifest, migrations)
        print(
            f"domain={manifest.domain_id} migrations={len(migrations)} "
            f"applied={len(applied)} oceanbase={profile['version']}"
        )
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
