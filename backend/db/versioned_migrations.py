"""Base-owned, versioned OceanBase/MySQL migration runner.

Application processes must not call this module during startup. Deployments invoke
``backend/scripts/run_migrations.py`` with the dedicated DDL credential.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path

from backend.governance import DomainRegistry, OwnershipError, load_registry

MIGRATION_RE = re.compile(
    r"^(?P<id>\d{12})_(?P<domain>base|craft|simulation|agent|device|knowledge)_(?P<name>[a-z0-9_]+)\.sql$"
)
LOCK_NAME = "ai00:database-migrations:v1"
LEDGER_TABLE = "workmanship_base_schema_migrations"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    migration_id: str
    domain: str
    name: str
    path: Path
    sql: str
    checksum: str


def split_sql(sql: str) -> list[str]:
    """Split MySQL statements while preserving semicolons inside strings/comments."""
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    line_comment = False
    block_comment = False
    i = 0
    while i < len(sql):
        char = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if line_comment:
            current.append(char)
            if char == "\n":
                line_comment = False
        elif block_comment:
            current.append(char)
            if char == "*" and nxt == "/":
                current.append(nxt)
                i += 1
                block_comment = False
        elif quote:
            current.append(char)
            if char == "\\" and nxt:
                current.append(nxt)
                i += 1
            elif char == quote:
                if nxt == quote:
                    current.append(nxt)
                    i += 1
                else:
                    quote = None
        elif char in ("'", '"', "`"):
            quote = char
            current.append(char)
        elif char == "-" and nxt == "-":
            line_comment = True
            current.extend((char, nxt))
            i += 1
        elif char == "#":
            line_comment = True
            current.append(char)
        elif char == "/" and nxt == "*":
            block_comment = True
            current.extend((char, nxt))
            i += 1
        elif char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        i += 1
    if quote or block_comment:
        raise MigrationError("unterminated SQL quote or block comment")
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def discover_migrations(directory: Path) -> list[Migration]:
    migrations: list[Migration] = []
    seen: set[str] = set()
    if not directory.exists():
        return migrations
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_RE.fullmatch(path.name)
        if not match:
            raise MigrationError(f"invalid migration filename: {path.name}")
        migration_id = match.group("id")
        if migration_id in seen:
            raise MigrationError(f"duplicate migration id: {migration_id}")
        seen.add(migration_id)
        raw = path.read_bytes()
        sql = raw.decode("utf-8")
        migrations.append(
            Migration(
                migration_id=migration_id,
                domain=match.group("domain"),
                name=match.group("name"),
                path=path,
                sql=sql,
                checksum=hashlib.sha256(raw).hexdigest(),
            )
        )
    return migrations


def _without_comments(statement: str) -> str:
    return re.sub(r"/\*.*?\*/|--[^\n]*|#[^\n]*", " ", statement, flags=re.DOTALL).strip()


def _is_resumable_ddl(statement: str) -> bool:
    """Return whether an OceanBase implicit-commit DDL is safe to replay."""
    normalized = " ".join(_without_comments(statement).split()).upper()
    return bool(
        re.match(r"^CREATE TABLE IF NOT EXISTS\b", normalized)
        or re.match(r"^CREATE (?:UNIQUE )?INDEX IF NOT EXISTS\b", normalized)
        or re.match(
            r"^ALTER TABLE\s+`?[A-Z0-9_]+`?\s+ADD COLUMN IF NOT EXISTS\b",
            normalized,
        )
    )


def _assert_oceanbase_ddl_policy(migration: Migration, statements: list[str]) -> None:
    """Reject SQL that cannot safely resume after OceanBase implicit commits."""
    from backend.db.oceanbase_compat import text_columns_with_defaults

    text_defaults = text_columns_with_defaults(migration.sql)
    if text_defaults:
        columns = ", ".join(sorted(set(text_defaults)))
        raise MigrationError(
            f"{migration.path.name} uses unsupported TEXT/BLOB defaults: {columns}"
        )
    for statement in statements:
        normalized = _without_comments(statement)
        if not normalized:
            continue
        if not _is_resumable_ddl(normalized):
            head = " ".join(normalized.split())[:120]
            raise MigrationError(
                f"{migration.path.name} contains non-resumable migration SQL: {head}"
            )


def validate_migration(migration: Migration, registry: DomainRegistry) -> None:
    statements = split_sql(migration.sql)
    meaningful = [statement for statement in statements if _without_comments(statement)]
    if not meaningful:
        raise MigrationError(f"empty migration: {migration.path.name}")
    tables = registry.tables_in(migration.sql)
    unowned = registry.validate_tables(tables)
    if unowned:
        raise OwnershipError(f"migration contains unowned tables: {unowned}")
    wrong_owner = sorted(
        table for table in tables if registry.table_owner(table).owner != migration.domain
    )
    if wrong_owner:
        raise OwnershipError(
            f"{migration.path.name} is owned by {migration.domain} but accesses {wrong_owner}"
        )
    _assert_oceanbase_ddl_policy(migration, meaningful)

def _scalar(row):
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _ensure_ledger(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
                migration_id VARCHAR(12) PRIMARY KEY,
                domain VARCHAR(32) NOT NULL,
                name VARCHAR(191) NOT NULL,
                checksum CHAR(64) NOT NULL,
                status VARCHAR(16) NOT NULL,
                duration_ms BIGINT NOT NULL DEFAULT 0,
                error TEXT NULL,
                applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        )
    conn.commit()


def apply_migrations(conn, directory: Path | None = None, registry: DomainRegistry | None = None) -> list[str]:
    registry = registry or load_registry()
    directory = directory or Path(__file__).with_name("migrations")
    migrations = discover_migrations(directory)
    for migration in migrations:
        validate_migration(migration, registry)

    with conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK(%s, %s)", (LOCK_NAME, 30))
        if _scalar(cur.fetchone()) != 1:
            raise MigrationError("could not acquire database migration lock")

    applied: list[str] = []
    try:
        _ensure_ledger(conn)
        with conn.cursor() as cur:
            cur.execute(f"SELECT migration_id, checksum, status FROM {LEDGER_TABLE}")
            rows = cur.fetchall()
        existing = {row["migration_id"] if isinstance(row, dict) else row[0]: row for row in rows}
        for migration in migrations:
            old = existing.get(migration.migration_id)
            if old:
                checksum = old["checksum"] if isinstance(old, dict) else old[1]
                status = old["status"] if isinstance(old, dict) else old[2]
                if checksum != migration.checksum and status == "applied":
                    raise MigrationError(f"checksum changed for applied migration {migration.migration_id}")
                if status == "applied":
                    continue
            started = time.monotonic()
            try:
                # OceanBase commits before and after DDL. Each statement is deliberately
                # replay-safe and committed independently so retries can resume safely.
                for statement in split_sql(migration.sql):
                    with conn.cursor() as cur:
                        cur.execute(statement)
                    conn.commit()
                duration = int((time.monotonic() - started) * 1000)
                with conn.cursor() as cur:
                    cur.execute(
                        f"""INSERT INTO {LEDGER_TABLE}
                            (migration_id, domain, name, checksum, status, duration_ms, error)
                            VALUES (%s, %s, %s, %s, 'applied', %s, NULL)
                            ON DUPLICATE KEY UPDATE status='applied', duration_ms=VALUES(duration_ms),
                                error=NULL, applied_at=CURRENT_TIMESTAMP(6)""",
                        (migration.migration_id, migration.domain, migration.name, migration.checksum, duration),
                    )
                conn.commit()
                applied.append(migration.migration_id)
            except Exception as exc:
                conn.rollback()
                duration = int((time.monotonic() - started) * 1000)
                with conn.cursor() as cur:
                    cur.execute(
                        f"""INSERT INTO {LEDGER_TABLE}
                            (migration_id, domain, name, checksum, status, duration_ms, error)
                            VALUES (%s, %s, %s, %s, 'failed', %s, %s)
                            ON DUPLICATE KEY UPDATE status='failed', duration_ms=VALUES(duration_ms),
                                error=VALUES(error), applied_at=CURRENT_TIMESTAMP(6)""",
                        (migration.migration_id, migration.domain, migration.name, migration.checksum, duration, str(exc)[:4000]),
                    )
                conn.commit()
                raise MigrationError(f"migration {migration.migration_id} failed: {exc}") from exc
        return applied
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
