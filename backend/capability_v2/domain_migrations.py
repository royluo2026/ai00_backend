"""Independent, replay-safe migration contracts for one domain database."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from backend.db.versioned_migrations import (
    MigrationError,
    assert_oceanbase_ddl_policy,
    canonicalize_migration_sql,
    normalize_oceanbase_sql,
    prepare_resumable_statement,
    split_sql,
    strip_sql_comments,
)

from .domain_manifest import DomainManifest


MIGRATION_FILE_RE = re.compile(r"^(?P<id>\d{4})_(?P<name>[a-z][a-z0-9_]*)\.sql$")
LEDGER_TABLE = "ai00_schema_migrations"
_QUALIFIED_IDENTIFIER_RE = re.compile(
    r"(?i)(?:`?[a-z_][a-z0-9_]*`?)\s*\.\s*(?:`?[a-z_][a-z0-9_]*`?)"
)


@dataclass(frozen=True)
class DomainMigration:
    migration_id: str
    name: str
    path: Path
    sql: str
    checksum: str
    artifact_version: str


def _without_string_literals(statement: str) -> str:
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(statement):
        char = statement[index]
        following = statement[index + 1] if index + 1 < len(statement) else ""
        if quote:
            result.append(" ")
            if char == "\\" and following:
                result.append(" ")
                index += 1
            elif char == quote:
                if following == quote:
                    result.append(" ")
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"'}:
            quote = char
            result.append(" ")
        else:
            result.append(char)
        index += 1
    return "".join(result)


def _validate_domain_sql(path: Path, sql: str) -> None:
    statements = split_sql(sql)
    meaningful = [strip_sql_comments(statement) for statement in statements]
    meaningful = [statement for statement in meaningful if statement]
    if not meaningful:
        raise MigrationError(f"empty migration: {path.name}")
    for statement in meaningful:
        normalized = " ".join(statement.split()).upper()
        if normalized.startswith("CREATE DATABASE ") or normalized.startswith("USE "):
            raise MigrationError(f"database_scope_forbidden: {path.name}")
        if normalized.startswith("GRANT ") or normalized.startswith("REVOKE "):
            raise MigrationError(f"database_privilege_forbidden: {path.name}")
        if _QUALIFIED_IDENTIFIER_RE.search(_without_string_literals(statement)):
            raise MigrationError(f"cross_database_identifier: {path.name}")
    assert_oceanbase_ddl_policy(path, sql)


def discover_domain_migrations(
    root: Path,
    manifest: DomainManifest,
) -> tuple[DomainMigration, ...]:
    directory = (root / manifest.database.migration_path).resolve()
    if not directory.exists():
        return ()
    migrations: list[DomainMigration] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.sql"), key=lambda item: item.name):
        match = MIGRATION_FILE_RE.fullmatch(path.name)
        if not match:
            raise MigrationError(f"invalid migration filename: {path.name}")
        migration_id = match.group("id")
        if migration_id in seen:
            raise MigrationError(f"duplicate migration id: {migration_id}")
        seen.add(migration_id)
        raw = path.read_bytes()
        try:
            canonical_sql = canonicalize_migration_sql(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise MigrationError(f"migration must be UTF-8: {path.name}") from exc
        sql = normalize_oceanbase_sql(canonical_sql)
        _validate_domain_sql(path, sql)
        migrations.append(DomainMigration(
            migration_id=migration_id,
            name=match.group("name"),
            path=path,
            sql=sql,
            checksum=hashlib.sha256(canonical_sql.encode("utf-8")).hexdigest(),
            artifact_version=manifest.artifact.version,
        ))
    return tuple(migrations)


def _scalar(row):
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _ensure_ledger(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
                migration_id CHAR(4) PRIMARY KEY,
                name VARCHAR(191) NOT NULL,
                checksum CHAR(64) NOT NULL,
                applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                artifact_version VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        )
    conn.commit()


def apply_domain_migrations(
    conn,
    manifest: DomainManifest,
    migrations: tuple[DomainMigration, ...],
) -> tuple[str, ...]:
    for migration in migrations:
        if migration.artifact_version != manifest.artifact.version:
            raise MigrationError(
                f"artifact_version_mismatch: {migration.path.name}"
            )
        _validate_domain_sql(migration.path, migration.sql)

    lock_name = f"ai00:migrations:{manifest.domain_id}:v1"
    with conn.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", (lock_name, 30))
        if _scalar(cursor.fetchone()) != 1:
            raise MigrationError(f"could not acquire domain migration lock: {manifest.domain_id}")

    applied: list[str] = []
    try:
        _ensure_ledger(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT migration_id, checksum, artifact_version FROM {LEDGER_TABLE}"
            )
            rows = cursor.fetchall()
        existing = {
            (row["migration_id"] if isinstance(row, dict) else row[0]): row
            for row in rows
        }
        for migration in migrations:
            row = existing.get(migration.migration_id)
            if row is not None:
                checksum = row["checksum"] if isinstance(row, dict) else row[1]
                if checksum != migration.checksum:
                    raise MigrationError(
                        f"checksum changed for applied migration {migration.migration_id}"
                    )
                continue
            try:
                for statement in split_sql(migration.sql):
                    prepared = prepare_resumable_statement(conn, statement)
                    if prepared is None:
                        continue
                    with conn.cursor() as cursor:
                        cursor.execute(prepared)
                    conn.commit()
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""INSERT INTO {LEDGER_TABLE}
                            (migration_id, name, checksum, artifact_version)
                            VALUES (%s, %s, %s, %s)""",
                        (
                            migration.migration_id,
                            migration.name,
                            migration.checksum,
                            migration.artifact_version,
                        ),
                    )
                conn.commit()
                applied.append(migration.migration_id)
            except Exception as exc:
                conn.rollback()
                if isinstance(exc, MigrationError):
                    raise
                raise MigrationError(
                    f"domain migration {migration.migration_id} failed: {exc}"
                ) from exc
        return tuple(applied)
    finally:
        with conn.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


__all__ = [
    "DomainMigration",
    "LEDGER_TABLE",
    "MigrationError",
    "apply_domain_migrations",
    "discover_domain_migrations",
]
