"""Independent, replay-safe migration contracts for one domain database."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from backend.db.versioned_migrations import (
    MigrationError,
    assert_historical_upload_triggers,
    assert_oceanbase_ddl_policy,
    canonicalize_migration_sql,
    normalize_oceanbase_sql,
    prepare_resumable_statement,
    split_sql,
    strip_sql_comments,
)
from backend.db.table_prefix import rewrite_sql

from .domain_manifest import DomainManifest


MIGRATION_FILE_RE = re.compile(r"^(?P<id>\d{4})_(?P<name>[a-z][a-z0-9_]*)\.sql$")
LEDGER_TABLE = "ai00_{domain_id}_schema_migrations"
_HISTORICAL_SIMULATION_0004 = "be3e9cefefa42b1fc196ffdf275d4740d30d8acffff0e80dc0408008e03ada04"
_HISTORICAL_SIMULATION_0033 = "92b0b1d5fd7551dd96fd64a7dbf4d2b8da72ff2cda0822e2939864979ca31931"
_HISTORICAL_BASE_0004 = "8da1d92e0fb3743ab8034edf8d97cdcda0be1db48f2ba259aee196c5c7a31a61"
_QUALIFIED_IDENTIFIER_RE = re.compile(
    r"(?i)(?:`?[a-z_][a-z0-9_]*`?)\s*\.\s*(?:`?[a-z_][a-z0-9_]*`?)"
)


def _split_multi_add_column_alters(sql: str) -> str:
    """Emit one ADD COLUMN per ALTER for OceanBase compatibility."""
    expanded: list[str] = []
    for statement in split_sql(sql):
        match = re.match(
            r"(?is)^(?P<head>\s*ALTER\s+TABLE\s+`?[A-Z0-9_]+`?\s+)"
            r"(?P<body>ADD\s+COLUMN\s+.+)$",
            strip_sql_comments(statement),
        )
        if not match:
            expanded.append(statement)
            continue
        clauses = re.split(r",\s*(?=ADD\s+COLUMN\b)", match.group("body"), flags=re.I)
        expanded.extend(match.group("head") + clause for clause in clauses)
    return ";\n".join(expanded) + (";" if expanded else "")


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
        checksum = hashlib.sha256(canonical_sql.encode("utf-8")).hexdigest()
        sql = normalize_oceanbase_sql(canonical_sql)
        if (manifest.domain_id == "base" and path.name == "0004_historical_uploads.sql"
                and checksum == _HISTORICAL_BASE_0004):
            sql = re.sub(
                r"(?im)^(CREATE TRIGGER base_historical_uploads_no_(?:update|delete)\b)",
                r"-- AI00: RESUMABLE CREATE TRIGGER\n\1", sql,
            )
        # 0004 was released before resumable ADD COLUMN syntax became mandatory.
        # Preserve its ledger checksum byte-for-byte while normalizing only the
        # executable form; 0006 carries the forward compatibility DDL.
        if (
            manifest.domain_id == "simulation"
            and migration_id == "0004"
            and checksum == _HISTORICAL_SIMULATION_0004
        ):
            sql = re.sub(r"\bADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)",
                         "ADD COLUMN IF NOT EXISTS ", sql, flags=re.I)
        if (
            manifest.domain_id == "simulation"
            and path.name == "0033_cloud_model_cache_pinned_query.sql"
            and checksum == _HISTORICAL_SIMULATION_0033
        ):
            sql = re.sub(r"\bADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)",
                         "ADD COLUMN IF NOT EXISTS ", sql, flags=re.I)
            sql = re.sub(r"\bCREATE\s+INDEX\s+(?!IF\s+NOT\s+EXISTS)",
                         "CREATE INDEX IF NOT EXISTS ", sql, flags=re.I)
        sql = _split_multi_add_column_alters(sql)
        _validate_domain_sql(path, sql)
        migrations.append(DomainMigration(
            migration_id=migration_id,
            name=match.group("name"),
            path=path,
            sql=sql,
            checksum=checksum,
            artifact_version=manifest.artifact.version,
        ))
    return tuple(migrations)


def _scalar(row):
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _ledger_table(manifest: DomainManifest) -> str:
    return LEDGER_TABLE.format(domain_id=manifest.domain_id)


def _ensure_ledger(conn, ledger_table: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {ledger_table} (
                migration_id CHAR(4) PRIMARY KEY,
                name VARCHAR(191) NOT NULL,
                checksum CHAR(64) NOT NULL,
                applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                artifact_version VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        )
    conn.commit()


def _normalized_generation_expression(expression: object) -> str | None:
    if not isinstance(expression, str):
        return None
    normalized: list[str] = []
    quoted = False
    index = 0
    while index < len(expression):
        character = expression[index]
        if quoted:
            normalized.append(character)
            if character == "\\" and index + 1 < len(expression):
                index += 1
                normalized.append(expression[index])
            elif character == "'":
                if index + 1 < len(expression) and expression[index + 1] == "'":
                    index += 1
                    normalized.append(expression[index])
                else:
                    quoted = False
        elif character == "'":
            quoted = True
            normalized.append(character)
        elif expression[index:index + 8].lower() == "_utf8mb4" and expression[index + 8:index + 9] == "'":
            index += 7
        elif character not in "` \t\r\n":
            normalized.append(character.lower())
        index += 1
    return None if quoted else "".join(normalized)


def _assert_simulation_0033_columns(conn, *, require_existing: bool) -> None:
    table = rewrite_sql("workmanship_sim_cloud_cache_nodes")
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME, "
            "EXTRA FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s "
            "AND COLUMN_NAME IN (%s, %s)",
            (table, "parent_node_key", "sibling_order"),
        )
        rows = cursor.fetchall()
    expected = {
        "parent_node_key": (
            {"varchar(128)"}, "utf8mb4", "utf8mb4_bin",
            "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.parent_occurrence_id')),'null')",
        ),
        "sibling_order": (
            {"int", "int(11)"}, None, None,
            "CAST(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.child_order')) AS UNSIGNED)",
        ),
    }
    seen: set[str] = set()
    for row in rows:
        fields = tuple(row[name] for name in (
            "COLUMN_NAME", "COLUMN_TYPE", "CHARACTER_SET_NAME", "COLLATION_NAME",
            "EXTRA",
        )) if isinstance(row, dict) else tuple(row)
        if len(fields) != 5 or not isinstance(fields[0], str):
            raise MigrationError("simulation_0033_column_definition_mismatch")
        name = fields[0].lower()
        if name not in expected or name in seen:
            raise MigrationError("simulation_0033_column_definition_mismatch")
        seen.add(name)
        column_types, charset, collation, _expression = expected[name]
        if (not isinstance(fields[1], str) or fields[1].lower() not in column_types or
                fields[2] != charset or fields[3] != collation or
                not isinstance(fields[4], str) or fields[4].upper().split() != ["STORED", "GENERATED"]):
            raise MigrationError("simulation_0033_column_definition_mismatch")
    if require_existing and seen != expected.keys():
        raise MigrationError("simulation_0033_columns_missing")
    if seen:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW CREATE TABLE `{table}`")
            definition = cursor.fetchone()
        definition_table = (definition.get("Table") if isinstance(definition, dict)
                            else definition[0] if isinstance(definition, (tuple, list)) and len(definition) == 2
                            else None)
        create_sql = (definition.get("Create Table") if isinstance(definition, dict)
                      else definition[1] if isinstance(definition, (tuple, list)) and len(definition) == 2
                      else None)
        if (not isinstance(definition_table, str) or definition_table.lower() != table.lower() or
                not isinstance(create_sql, str) or len(create_sql) > 2 * 1024 * 1024 or
                not re.match(rf"^CREATE\s+TABLE\s+`?{re.escape(table)}`?\s*\(", create_sql, re.I)):
            raise MigrationError("simulation_0033_column_definition_mismatch")
        for name in seen:
            lines = [line for line in create_sql.splitlines()
                     if re.match(rf"^\s*`?{name}`?\s", line, re.I)]
            if len(lines) != 1:
                raise MigrationError("simulation_0033_column_definition_mismatch")
            match = re.search(r"(?:GENERATED\s+ALWAYS\s+)?AS\s*\((.*)\)\s+STORED\s*,?\s*$",
                              lines[0], re.I)
            if not match or _normalized_generation_expression(match.group(1)) != \
                    _normalized_generation_expression(expected[name][3]):
                raise MigrationError("simulation_0033_column_definition_mismatch")


def _assert_simulation_0033_index(conn, *, require_existing: bool) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME, SEQ_IN_INDEX, NON_UNIQUE, SUB_PART "
            "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME=%s AND INDEX_NAME=%s ORDER BY SEQ_IN_INDEX",
            (rewrite_sql("workmanship_sim_cloud_cache_nodes"), "ix_cloud_cache_parent_order"),
        )
        rows = cursor.fetchall()
    if not rows:
        if require_existing:
            raise MigrationError("simulation_0033_index_missing")
        return
    actual = tuple(
        (
            str(row["COLUMN_NAME"] if isinstance(row, dict) else row[0]).lower(),
            int(row["SEQ_IN_INDEX"] if isinstance(row, dict) else row[1]),
            int(row["NON_UNIQUE"] if isinstance(row, dict) else row[2]),
            row["SUB_PART"] if isinstance(row, dict) else row[3],
        )
        for row in rows
    )
    expected = tuple((column, position, 1, None) for position, column in enumerate(
        ("batch_id", "parent_node_key", "sibling_order", "node_key"), 1
    ))
    if actual != expected:
        raise MigrationError("simulation_0033_index_definition_mismatch")


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
    ledger_table = _ledger_table(manifest)
    named_lock_acquired = False
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, %s)", (lock_name, 30))
            if _scalar(cursor.fetchone()) != 1:
                raise MigrationError(f"could not acquire domain migration lock: {manifest.domain_id}")
            named_lock_acquired = True
    except Exception as exc:
        if not (exc.args and exc.args[0] == 1305 and "GET_LOCK" in str(exc)):
            raise

    applied: list[str] = []
    try:
        _ensure_ledger(conn, ledger_table)
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT migration_id, checksum, artifact_version FROM {ledger_table}"
            )
            rows = cursor.fetchall()
        existing = {
            (row["migration_id"] if isinstance(row, dict) else row[0]): row
            for row in rows
        }
        for migration in migrations:
            row = existing.get(migration.migration_id)
            check_historical_triggers = (
                manifest.domain_id == "base"
                and migration.migration_id == "0004"
                and migration.name == "historical_uploads"
                and migration.checksum == _HISTORICAL_BASE_0004
            )
            check_historical_index = (
                manifest.domain_id == "simulation"
                and migration.migration_id == "0033"
                and migration.name == "cloud_model_cache_pinned_query"
                and migration.checksum == _HISTORICAL_SIMULATION_0033
            )
            if row is not None:
                checksum = row["checksum"] if isinstance(row, dict) else row[1]
                if checksum != migration.checksum:
                    raise MigrationError(
                        f"checksum changed for applied migration {migration.migration_id}"
                    )
                if check_historical_index:
                    _assert_simulation_0033_columns(conn, require_existing=True)
                    _assert_simulation_0033_index(conn, require_existing=True)
                if check_historical_triggers:
                    assert_historical_upload_triggers(conn, require_existing=True)
                continue
            try:
                if check_historical_triggers:
                    assert_historical_upload_triggers(conn, require_existing=False)
                if check_historical_index:
                    _assert_simulation_0033_columns(conn, require_existing=False)
                    _assert_simulation_0033_index(conn, require_existing=False)
                for statement in split_sql(migration.sql):
                    prepared = prepare_resumable_statement(conn, statement)
                    if prepared is None:
                        continue
                    with conn.cursor() as cursor:
                        cursor.execute(prepared)
                    conn.commit()
                if check_historical_triggers:
                    assert_historical_upload_triggers(conn, require_existing=True)
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""INSERT INTO {ledger_table}
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
        if named_lock_acquired:
            with conn.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


__all__ = [
    "DomainMigration",
    "LEDGER_TABLE",
    "MigrationError",
    "apply_domain_migrations",
    "discover_domain_migrations",
]
