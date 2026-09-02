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
    r"^(?P<id>\d{12})_(?P<domain>base|craft|digital_model|project_management|simulation|agent|device|ontology|knowledge)_(?P<name>[a-z0-9_]+)\.sql$"
)
LOCK_NAME = "ai00:database-migrations:v1"
LEDGER_TABLE = "workmanship_base_schema_migrations"
KNOWN_LEGACY_CHECKSUMS = {
    "202608030010": ("2647a9edcc06a4f37aa60e4338e71d4e0bb9a89bb2a003b078d3f9c743b51ee2",),
    "202608040001": ("1f6032096a447ed34bdb89d151e57f6706ff7ed7332438f334e5fc47d9f62020",),
    "202608040003": ("7a35e7999a9154bee2f6f353df417ce97f804e8788f05d753d39f347c1ea7d54",),
    "202608100004": ("33c21eee3819f795dd226191363ac35a8bf57a6d72a7fba97ddcb9ab82d5b6af",),
    "202608280001": ("2a1466e75b99b131ca2b8e73e83b17a6530694733c1e55aee629a8ca5ee13b65",),
    "202608280002": ("a2acc98dffb92258012fcd9e0d8865055cfb91d672e0e00403e01e3908acce64",),
    "202608280003": ("a14401c8c57e0aafa419772487d2fc560c77edfa6f8e0b463142c50374f49a48",),
}


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
    legacy_checksums: tuple[str, ...] = ()


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


def canonicalize_migration_sql(sql: str) -> str:
    """Make migration checksums independent of Git/OS line-ending conversion."""
    return sql.replace("\r\n", "\n").replace("\r", "\n")


def normalize_oceanbase_sql(sql: str) -> str:
    """Remove MySQL defaults that OceanBase 4.3.5 rejects, without changing checksums."""
    return re.sub(
        r"\bJSON(?P<nullability>\s+(?:NOT\s+NULL|NULL))?\s+DEFAULT\s+"
        r"\(JSON_(?:OBJECT|ARRAY)\(\)\)",
        lambda match: "JSON" + (match.group("nullability") or ""),
        sql,
        flags=re.I,
    )

def bootstrap_statements(sql: str) -> list[str]:
    """Return baseline statements scoped to the database selected by the URL."""
    result: list[str] = []
    for statement in split_sql(sql):
        normalized = " ".join(strip_sql_comments(statement).split()).upper()
        if not normalized:
            continue
        if normalized.startswith("CREATE DATABASE ") or normalized.startswith("USE "):
            continue
        result.append(statement)
    return result


def apply_bootstrap_schema(conn, path: Path) -> bool:
    """Create the baseline once; safely resume after OceanBase implicit commits."""
    marker_table = "workmanship_display_id_counters"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
            (marker_table,),
        )
        row = cur.fetchone()
    if int(_scalar(row)) > 0:
        return False

    sql = path.read_text(encoding="utf-8")
    for statement in bootstrap_statements(sql):
        try:
            with conn.cursor() as cur:
                cur.execute(statement)
            conn.commit()
        except Exception as exc:
            # Standalone CREATE INDEX lacks IF NOT EXISTS in OceanBase. Retrying a
            # partially committed bootstrap may therefore encounter a duplicate.
            if getattr(exc, "args", ()) and exc.args[0] == 1061:
                conn.rollback()
                continue
            conn.rollback()
            raise MigrationError(f"baseline schema failed: {exc}") from exc
    return True

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
        canonical_sql = canonicalize_migration_sql(raw.decode("utf-8"))
        sql = normalize_oceanbase_sql(canonical_sql)
        migrations.append(
            Migration(
                migration_id=migration_id,
                domain=match.group("domain"),
                name=match.group("name"),
                path=path,
                sql=sql,
                checksum=hashlib.sha256(canonical_sql.encode("utf-8")).hexdigest(),
                legacy_checksums=tuple({
                    hashlib.sha256(raw).hexdigest(),
                    hashlib.sha256(canonical_sql.replace("\n", "\r\n").encode("utf-8")).hexdigest(),
                    *KNOWN_LEGACY_CHECKSUMS.get(migration_id, ()),
                }),
            )
        )
    return migrations


def strip_sql_comments(statement: str) -> str:
    result: list[str] = []
    quote: str | None = None
    line_comment = False
    block_comment = False
    index = 0
    while index < len(statement):
        char = statement[index]
        following = statement[index + 1] if index + 1 < len(statement) else ""
        if line_comment:
            if char in "\r\n":
                line_comment = False
                result.append(char)
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                result.append(" ")
                index += 1
        elif quote:
            result.append(char)
            if char == "\\" and following:
                index += 1
                result.append(following)
            elif char == quote:
                if following == quote:
                    index += 1
                    result.append(following)
                else:
                    quote = None
        elif char in "'\"`":
            quote = char
            result.append(char)
        elif char == "-" and following == "-":
            line_comment = True
            result.append(" ")
            index += 1
        elif char == "#":
            line_comment = True
            result.append(" ")
        elif char == "/" and following == "*":
            block_comment = True
            result.append(" ")
            index += 1
        else:
            result.append(char)
        index += 1
    return "".join(result).strip()


def is_resumable_ddl(statement: str) -> bool:
    """Return whether an OceanBase implicit-commit DDL is safe to replay."""
    normalized = " ".join(strip_sql_comments(statement).split()).upper()
    marked_backfill = "AI00: RESUMABLE BACKFILL" in statement.upper()
    marked_foreign_key_drop = "AI00: RESUMABLE DROP FOREIGN KEY" in statement.upper()
    return bool(
        re.match(r"^CREATE TABLE IF NOT EXISTS\b", normalized)
        or re.match(r"^CREATE (?:UNIQUE )?INDEX IF NOT EXISTS\b", normalized)
        or re.match(
            r"^ALTER TABLE\s+`?[A-Z0-9_]+`?\s+ADD COLUMN IF NOT EXISTS\b",
            normalized,
        )
        or re.match(
            r"^ALTER TABLE\s+`?[A-Z0-9_]+`?\s+MODIFY COLUMN\s+`?[A-Z0-9_]+`?.*\bNOT NULL\b",
            normalized,
        )
        or re.match(
            r"^ALTER TABLE\s+`?[A-Z0-9_]+`?\s+DROP PRIMARY KEY\s*,\s*ADD PRIMARY KEY\s*\(",
            normalized,
        )
        or (
            marked_foreign_key_drop
            and re.match(
                r"^ALTER TABLE\s+`?[A-Z0-9_]+`?\s+DROP FOREIGN KEY\s+`?[A-Z0-9_]+`?$",
                normalized,
            )
        )
        or (marked_backfill and re.match(r"^UPDATE\b", normalized))
        or (marked_backfill and re.match(r"^INSERT\b.*\bON DUPLICATE KEY UPDATE\b", normalized))
    )


def prepare_resumable_statement(conn, statement: str) -> str | None:
    """Translate declarative IF NOT EXISTS DDL for OceanBase 4.3.5."""
    if re.search(r"\bworkmanship_base_self_annotations\s+a\b", statement, re.I):
        # The legacy annotation table can retain utf8mb4_general_ci while the
        # governed state/idempotency/audit tables use utf8mb4_unicode_ci.
        # Keep the immutable migration artifact unchanged and make its one-time
        # cross-table backfills explicit for OceanBase error 1267.
        statement = re.sub(
            r"\ba\.(item_gid|user_gid)\s*=\s*([a-z]\.(?:item_gid|user_gid|actor_gid))",
            r"a.\1 COLLATE utf8mb4_unicode_ci=\2",
            statement,
            flags=re.I,
        )
        statement = re.sub(
            r"\b([a-z]\.(?:gid|item_gid|user_gid|actor_gid))\s*=\s*a\.(item_gid|user_gid)",
            r"\1=a.\2 COLLATE utf8mb4_unicode_ci",
            statement,
            flags=re.I,
        )

    if re.search(
        r"\bUPDATE\s+workmanship_know_craft_rules\s+SET\s+owner_user_gid\s*=\s*creator_gid\b",
        strip_sql_comments(statement),
        re.I,
    ):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                ("workmanship_know_craft_rules", "creator_gid"),
            )
            creator_exists = int(_scalar(cur.fetchone())) > 0
        if not creator_exists:
            return None

    add_column = re.search(
        r"\bALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?\s+ADD\s+COLUMN\s+"
        r"IF\s+NOT\s+EXISTS\s+`?([A-Za-z0-9_]+)`?",
        statement,
        re.I,
    )
    if add_column:
        table, column = add_column.groups()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                (table, column),
            )
            exists = int(_scalar(cur.fetchone())) > 0
        if exists:
            return None
        return re.sub(r"\bADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b", "ADD COLUMN", statement, count=1, flags=re.I)

    create_index = re.search(
        r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+"
        r"`?([A-Za-z0-9_]+)`?\s+ON\s+`?([A-Za-z0-9_]+)`?",
        statement,
        re.I,
    )
    if create_index:
        index, table = create_index.groups()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s",
                (table, index),
            )
            exists = int(_scalar(cur.fetchone())) > 0
        if exists:
            return None
        return re.sub(r"\bINDEX\s+IF\s+NOT\s+EXISTS\b", "INDEX", statement, count=1, flags=re.I)

    modify_not_null = re.search(
        r"\bALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?\s+MODIFY\s+COLUMN\s+"
        r"`?([A-Za-z0-9_]+)`?.*\bNOT\s+NULL\b",
        strip_sql_comments(statement),
        re.I | re.S,
    )
    if modify_not_null:
        table, column = modify_not_null.groups()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT IS_NULLABLE, COLUMN_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                (table, column),
            )
            row = cur.fetchone()
        if row is not None:
            nullable = str(row["IS_NULLABLE"] if isinstance(row, dict) else row[0]).upper()
            if nullable == "NO":
                desired_binary = re.search(r"\bVARBINARY\s*\(\s*\d+\s*\)", statement, re.I)
                if desired_binary is None:
                    return None
                column_type = (
                    row.get("COLUMN_TYPE") if isinstance(row, dict)
                    else row[1] if len(row) > 1 else None
                )
                desired_type = re.sub(r"\s+", "", desired_binary.group(0)).lower()
                if column_type is not None and re.sub(r"\s+", "", str(column_type)).lower() == desired_type:
                    return None
        return statement

    primary_key_change = re.search(
        r"\bALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?\s+DROP\s+PRIMARY\s+KEY\s*,\s*"
        r"ADD\s+PRIMARY\s+KEY\s*\(([^)]+)\)",
        strip_sql_comments(statement),
        re.I | re.S,
    )
    if primary_key_change:
        table, raw_columns = primary_key_change.groups()
        desired = tuple(item.strip().strip("`").lower() for item in raw_columns.split(","))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND INDEX_NAME='PRIMARY' "
                "ORDER BY SEQ_IN_INDEX",
                (table,),
            )
            rows = cur.fetchall()
        current = tuple(
            str(row["COLUMN_NAME"] if isinstance(row, dict) else row[0]).lower()
            for row in rows
        )
        if current == desired:
            return None
        return statement

    foreign_key_drop = re.search(
        r"\bALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?\s+DROP\s+FOREIGN\s+KEY\s+"
        r"`?([A-Za-z0-9_]+)`?",
        strip_sql_comments(statement),
        re.I,
    )
    if "AI00: RESUMABLE DROP FOREIGN KEY" in statement.upper() and foreign_key_drop:
        table, constraint = foreign_key_drop.groups()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME=%s "
                "AND CONSTRAINT_NAME=%s AND CONSTRAINT_TYPE='FOREIGN KEY'",
                (table, constraint),
            )
            exists = int(_scalar(cur.fetchone())) > 0
        return statement if exists else None

    normalized = strip_sql_comments(statement)
    if re.match(r"^UPDATE\s+workmanship_know_craft_rules\b", normalized, re.I) and re.search(r"\bcreator_gid\b", normalized, re.I):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                ("workmanship_know_craft_rules", "creator_gid"),
            )
            if int(_scalar(cur.fetchone())) == 0:
                return None

    return statement

def assert_oceanbase_ddl_policy(path: Path, sql: str) -> None:
    """Reject SQL that cannot safely resume after OceanBase implicit commits."""
    from backend.db.oceanbase_compat import text_columns_with_defaults

    statements = split_sql(sql)
    text_defaults = text_columns_with_defaults(sql)
    if text_defaults:
        columns = ", ".join(sorted(set(text_defaults)))
        raise MigrationError(
            f"{path.name} uses unsupported TEXT/BLOB defaults: {columns}"
        )
    for statement in statements:
        normalized = strip_sql_comments(statement)
        if not normalized:
            continue
        if not is_resumable_ddl(statement):
            head = " ".join(normalized.split())[:120]
            raise MigrationError(
                f"{path.name} contains non-resumable migration SQL: {head}"
            )


def validate_migration(migration: Migration, registry: DomainRegistry) -> None:
    statements = split_sql(migration.sql)
    meaningful = [statement for statement in statements if strip_sql_comments(statement)]
    if not meaningful:
        raise MigrationError(f"empty migration: {migration.path.name}")
    tables = registry.tables_in(migration.sql)
    unowned = registry.validate_tables(tables)
    if unowned:
        raise OwnershipError(f"migration contains unowned tables: {unowned}")
    effective_owner = registry.migration_owner(migration.migration_id, migration.domain)
    wrong_owner = sorted(
        table for table in tables
        if registry.table_owner(table).owner != effective_owner
        and not registry.migration_allows_table(migration.migration_id, table)
    )
    if wrong_owner:
        raise OwnershipError(
            f"{migration.path.name} is owned by {effective_owner} but accesses {wrong_owner}"
        )
    assert_oceanbase_ddl_policy(migration.path, migration.sql)

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
                valid_checksums = {migration.checksum, *migration.legacy_checksums} - {""}
                if checksum not in valid_checksums and status == "applied":
                    raise MigrationError(f"checksum changed for applied migration {migration.migration_id}")
                if status == "applied":
                    continue
            started = time.monotonic()
            effective_owner = registry.migration_owner(migration.migration_id, migration.domain)
            try:
                # OceanBase commits before and after DDL. Each statement is deliberately
                # replay-safe and committed independently so retries can resume safely.
                for statement in split_sql(migration.sql):
                    prepared = prepare_resumable_statement(conn, statement)
                    if prepared is None:
                        continue
                    with conn.cursor() as cur:
                        cur.execute(prepared)
                    conn.commit()
                duration = int((time.monotonic() - started) * 1000)
                with conn.cursor() as cur:
                    cur.execute(
                        f"""INSERT INTO {LEDGER_TABLE}
                            (migration_id, domain, name, checksum, status, duration_ms, error)
                            VALUES (%s, %s, %s, %s, 'applied', %s, NULL)
                            ON DUPLICATE KEY UPDATE checksum=VALUES(checksum), status='applied',
                                duration_ms=VALUES(duration_ms), error=NULL,
                                applied_at=CURRENT_TIMESTAMP(6)""",
                        (migration.migration_id, effective_owner, migration.name, migration.checksum, duration),
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
                        (migration.migration_id, effective_owner, migration.name, migration.checksum, duration, str(exc)[:4000]),
                    )
                conn.commit()
                raise MigrationError(f"migration {migration.migration_id} failed: {exc}") from exc
        return applied
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
