#!/usr/bin/env python3
"""Apply the isolated Capability Governance test schema with the test DDL account."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote, urlparse


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.db.oceanbase_compat import verify_live_server
from backend.db.versioned_migrations import (
    MigrationError,
    assert_oceanbase_ddl_policy,
    canonicalize_migration_sql,
    normalize_oceanbase_sql,
    prepare_resumable_statement,
    split_sql,
    strip_sql_comments,
)


MIGRATION_DIRECTORY = Path("backend/db/migrations/test_governance")
MIGRATION_FILE_RE = re.compile(r"^(?P<id>\d{4})_(?P<name>[a-z][a-z0-9_]*)\.sql$")
LEDGER_TABLE = "workmanship_base_capability_governance_migrations"
LOCK_NAME = "ai00:capability-governance:test:v1"
GOVERNANCE_TABLES = (
    "workmanship_base_capability_entries",
    "workmanship_base_capability_versions",
    "workmanship_base_capability_scan_runs",
    "workmanship_base_capability_snapshots",
    "workmanship_base_capability_snapshot_entries",
    "workmanship_base_capability_implementation_nodes",
    "workmanship_base_capability_bindings",
    "workmanship_base_capability_implementation_relations",
    "workmanship_base_capability_evidence",
    "workmanship_base_capability_test_runs",
    "workmanship_base_capability_test_results",
    "workmanship_base_capability_health_rollups",
    "workmanship_base_capability_analysis_runs",
    "workmanship_base_capability_findings",
    "workmanship_base_capability_finding_subjects",
    "workmanship_base_capability_change_proposals",
    "workmanship_base_capability_reviews",
    "workmanship_base_capability_waivers",
    "workmanship_base_capability_release_reports",
    "workmanship_base_capability_audit_events",
    "workmanship_base_capability_worker_leases",
    "workmanship_base_capability_business_purposes",
    "workmanship_base_capability_business_rules",
    "workmanship_base_capability_relation_candidates",
    "workmanship_base_capability_business_reviews",
    "workmanship_base_capability_business_review_requests",
    "workmanship_base_capability_standard_review_requests",
    "workmanship_base_capability_rule_effectiveness",
)


@dataclass(frozen=True)
class GovernanceMigration:
    migration_id: str
    name: str
    path: Path
    sql: str
    checksum: str


@dataclass(frozen=True)
class CompiledGovernanceMigrations:
    migrations: tuple[GovernanceMigration, ...]
    tables: tuple[str, ...]
    normalized_sql: str


def _scalar(row):
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _created_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    for statement in split_sql(sql):
        match = re.match(
            r"^\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z_][A-Za-z0-9_]*)`?\s*\(",
            strip_sql_comments(statement),
            re.I,
        )
        if match:
            tables.add(match.group(1))
    return tables


def compile_governance_migrations(root: Path = REPOSITORY_ROOT, *, table_prefix: str = "") -> CompiledGovernanceMigrations:
    """Compile the separate, UTF-8 governance stream without product schema discovery."""
    if table_prefix not in ("", "test_"):
        raise MigrationError("unsupported governance table prefix")
    directory = Path(root) / MIGRATION_DIRECTORY
    migrations: list[GovernanceMigration] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.sql"), key=lambda item: item.name):
        match = MIGRATION_FILE_RE.fullmatch(path.name)
        if not match:
            raise MigrationError(f"invalid governance migration filename: {path.name}")
        migration_id = match.group("id")
        if migration_id in seen:
            raise MigrationError(f"duplicate governance migration id: {migration_id}")
        seen.add(migration_id)
        try:
            canonical_sql = canonicalize_migration_sql(path.read_bytes().decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise MigrationError(f"governance migration must be UTF-8: {path.name}") from exc
        sql = normalize_oceanbase_sql(canonical_sql)
        assert_oceanbase_ddl_policy(path, sql)
        migrations.append(GovernanceMigration(
            migration_id=migration_id,
            name=match.group("name"),
            path=path,
            sql=sql,
            checksum=hashlib.sha256(canonical_sql.encode("utf-8")).hexdigest(),
        ))
    tables = set().union(*(_created_tables(item.sql) for item in migrations)) if migrations else set()
    entity_tables = tables - {LEDGER_TABLE}
    expected = set(GOVERNANCE_TABLES)
    if entity_tables != expected:
        raise MigrationError(
            f"governance table contract mismatch: missing={sorted(expected - entity_tables)}, extra={sorted(entity_tables - expected)}"
        )
    # Keep immutable source checksums; namespace is isolated by its own ledger.
    # Rewrite before metadata probes, including the Catalog backfill dependency.
    if table_prefix:
        migrations = [replace(item, sql=re.sub(
            r"(?<![A-Za-z0-9_])workmanship_", table_prefix + "workmanship_", item.sql,
        )) for item in migrations]
        entity_tables = {table_prefix + name for name in entity_tables}
    return CompiledGovernanceMigrations(
        migrations=tuple(migrations),
        tables=tuple(sorted(entity_tables)),
        normalized_sql="\n".join(item.sql for item in migrations),
    )


def _ledger_exists(connection, ledger_table: str = LEDGER_TABLE) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
            (ledger_table,),
        )
        return int(_scalar(cursor.fetchone())) > 0


def migrate(connection, *, table_prefix: str = "", root: Path = REPOSITORY_ROOT,
            externally_serialized: bool = False) -> tuple[str, ...]:
    """Apply verified governance migrations and return just-applied migration IDs."""
    compiled = compile_governance_migrations(root, table_prefix=table_prefix)
    ledger_table = table_prefix + LEDGER_TABLE
    lock_name = LOCK_NAME + (":" + table_prefix if table_prefix else "")
    named_lock_acquired = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, %s)", (lock_name, 30))
            if _scalar(cursor.fetchone()) != 1:
                raise MigrationError("could not acquire capability governance migration lock")
            named_lock_acquired = True
    except Exception as exc:
        if not (externally_serialized and exc.args and exc.args[0] == 1305
                and "GET_LOCK" in str(exc).upper()):
            raise
    applied: list[str] = []
    try:
        existing = {}
        if _ledger_exists(connection, ledger_table):
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT migration_id, checksum FROM {ledger_table}")
                rows = cursor.fetchall()
            existing = {
                row["migration_id"] if isinstance(row, dict) else row[0]: row
                for row in rows
            }
        for migration in compiled.migrations:
            row = existing.get(migration.migration_id)
            if row is not None:
                checksum = row["checksum"] if isinstance(row, dict) else row[1]
                if checksum != migration.checksum:
                    raise MigrationError(
                        f"checksum changed for applied governance migration {migration.migration_id}"
                    )
                continue
            try:
                for statement in split_sql(migration.sql):
                    prepared = prepare_resumable_statement(connection, statement)
                    if prepared is None:
                        continue
                    with connection.cursor() as cursor:
                        cursor.execute(prepared)
                    connection.commit()
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"INSERT INTO {ledger_table} (migration_id, name, checksum) VALUES (%s, %s, %s)",
                        (migration.migration_id, migration.name, migration.checksum),
                    )
                connection.commit()
                applied.append(migration.migration_id)
            except Exception as exc:
                connection.rollback()
                if isinstance(exc, MigrationError):
                    raise
                raise MigrationError(
                    f"governance migration {migration.migration_id} failed ({type(exc).__name__})"
                ) from exc
        return tuple(applied)
    finally:
        if named_lock_acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


def _connect_test_ddl(url: str):
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"mysql", "mysql+pymysql"}
        or not parsed.hostname
        or not parsed.username
        or not parsed.password
        or not parsed.path.removeprefix("/")
        or parsed.query
        or parsed.fragment
    ):
        raise MigrationError("invalid test governance DDL configuration")
    import pymysql

    return pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username),
        password=unquote(parsed.password),
        database=unquote(parsed.path.removeprefix("/")),
        charset="utf8mb4",
        autocommit=False,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = REPOSITORY_ROOT,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--externally-serialized", action="store_true",
                        help="operator guarantees one migration runner; permits unsupported GET_LOCK only")
    args = parser.parse_args(argv)
    environment = os.environ if environ is None else environ
    if environment.get("AI00_DEPLOYMENT_PROFILE") != "test-governance":
        raise MigrationError("Capability Governance migrations require AI00_DEPLOYMENT_PROFILE=test-governance")

    table_prefix = environment.get("TABLE_PREFIX", "")
    compiled = compile_governance_migrations(root, table_prefix=table_prefix)
    if args.check:
        print(f"profile=test-governance prefix={table_prefix or '(dedicated)'} migrations={len(compiled.migrations)} tables={len(compiled.tables)} mode=check")
        return 0

    ddl_url = str(environment.get("AI00_BASE_DDL_DB_URL", "")).strip()
    if not ddl_url:
        raise MigrationError("missing test governance DDL configuration")
    connection = _connect_test_ddl(ddl_url)
    try:
        profile = verify_live_server(connection)
        applied = migrate(connection, table_prefix=table_prefix, root=root,
                          externally_serialized=args.externally_serialized)
        print(
            f"profile=test-governance migrations={len(compiled.migrations)} tables={len(compiled.tables)} "
            f"applied={len(applied)} oceanbase={profile['version']}"
        )
    finally:
        connection.close()
    return 0


def _run_cli() -> int:
    try:
        return main()
    except Exception:
        print("capability governance migration command failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_run_cli())
