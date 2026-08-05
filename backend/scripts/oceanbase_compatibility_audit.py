#!/usr/bin/env python3
"""Static and optional live OceanBase MySQL-mode deployment gate."""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.oceanbase_compat import (
    MIN_OCEANBASE_VERSION_TEXT,
    CompatibilityIssue,
    assert_supported_server,
    audit_sql,
)
from backend.db.versioned_migrations import discover_migrations, validate_migration
from backend.governance import load_registry

SQL_SOURCE_ROOTS = (
    REPO_ROOT / "backend" / "capabilities",
    REPO_ROOT / "backend" / "routers",
    REPO_ROOT / "plugins",
)


def _python_sql_issues(path: Path) -> list[CompatibilityIssue]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [CompatibilityIssue("OB900", str(path), getattr(exc, "lineno", 1) or 1, f"cannot parse Python source: {exc}")]
    issues: list[CompatibilityIssue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in {"execute", "executemany"}:
            continue
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            sql = value.value
        elif isinstance(value, ast.JoinedStr):
            sql = "".join(part.value for part in value.values if isinstance(part, ast.Constant) and isinstance(part.value, str))
        else:
            continue
        for issue in audit_sql(path, sql):
            issues.append(CompatibilityIssue(issue.code, issue.path, node.lineno + issue.line - 1, issue.message))
    return issues


def static_audit() -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    registry = load_registry()
    migration_dir = REPO_ROOT / "backend" / "db" / "migrations"
    for migration in discover_migrations(migration_dir):
        try:
            validate_migration(migration, registry)
        except Exception as exc:
            issues.append(CompatibilityIssue("OB100", str(migration.path), 1, str(exc)))
        issues.extend(audit_sql(migration.path, migration.sql))
    bootstrap = REPO_ROOT / "backend" / "db" / "mysql_schema.sql"
    issues.extend(audit_sql(bootstrap, bootstrap.read_text(encoding="utf-8")))
    for root in SQL_SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            if "__pycache__" not in path.parts:
                issues.extend(_python_sql_issues(path))
    return sorted(set(issues), key=lambda item: (item.path, item.line, item.code, item.message))


def _row_value(row, preferred: str | None = None):
    if isinstance(row, dict):
        if preferred and preferred in row:
            return row[preferred]
        return list(row.values())[-1]
    return row[-1]


def live_audit(raw_url: str) -> list[str]:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise RuntimeError("AI00_DDL_DB_URL must be a mysql:// URL with an explicit database")
    import pymysql

    database = parsed.path.lstrip("/")
    conn = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    messages: list[str] = []
    lock_name = "ai00:oceanbase-compatibility-probe"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS version")
            version = str(_row_value(cur.fetchone(), "version"))
            cur.execute("SHOW VARIABLES LIKE 'ob_compatibility_mode'")
            mode_row = cur.fetchone()
            if not mode_row:
                raise RuntimeError("server does not expose ob_compatibility_mode; verify this is OceanBase")
            mode = str(_row_value(mode_row, "Value"))
            assert_supported_server(version, mode)
            messages.append(f"server={version}; mode={mode}; minimum={MIN_OCEANBASE_VERSION_TEXT}")
            cur.execute("SELECT GET_LOCK(%s, 0) AS acquired", (lock_name,))
            if int(_row_value(cur.fetchone(), "acquired")) != 1:
                raise RuntimeError("GET_LOCK capability probe failed")
            cur.execute("SELECT RELEASE_LOCK(%s) AS released", (lock_name,))
            if int(_row_value(cur.fetchone(), "released")) != 1:
                raise RuntimeError("RELEASE_LOCK capability probe failed")
            cur.execute(
                "SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND DATA_TYPE IN ('tinytext','text','mediumtext','longtext','tinyblob','blob','mediumblob','longblob','json') "
                "AND COLUMN_DEFAULT IS NOT NULL",
                (database,),
            )
            invalid = cur.fetchall()
            if invalid:
                names = ", ".join(f"{row['TABLE_NAME']}.{row['COLUMN_NAME']}" for row in invalid[:20])
                raise RuntimeError(f"live schema has TEXT/BLOB/JSON defaults: {names}")
            messages.append("GET_LOCK/RELEASE_LOCK and live TEXT/BLOB/JSON-default checks passed")
    finally:
        conn.close()
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect", action="store_true", help="also verify the server and live schema using AI00_DDL_DB_URL")
    args = parser.parse_args()
    issues = static_audit()
    if issues:
        for issue in issues:
            print(issue.render())
        print(f"OceanBase compatibility audit FAILED: {len(issues)} issue(s)")
        return 1
    print("OceanBase static compatibility audit passed")
    if args.connect:
        raw = os.environ.get("AI00_DDL_DB_URL", "")
        if not raw:
            raise SystemExit("AI00_DDL_DB_URL is required with --connect")
        for message in live_audit(raw):
            print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())