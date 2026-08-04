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
from backend.db.versioned_migrations import apply_migrations


def main() -> int:
    raw = os.environ.get("AI00_DDL_DB_URL", "")
    if not raw:
        raise SystemExit("AI00_DDL_DB_URL is required; application runtime credentials are refused")
    parsed = urlparse(raw)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise SystemExit("AI00_DDL_DB_URL must be a mysql:// URL with an explicit database")
    import pymysql

    conn = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        profile = verify_live_server(conn)
        print(f"OceanBase compatibility verified: {profile['version']} ({profile['compatibility_mode']})")
        applied = apply_migrations(conn)
        print(f"applied {len(applied)} migration(s): {', '.join(applied) or 'none'}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
