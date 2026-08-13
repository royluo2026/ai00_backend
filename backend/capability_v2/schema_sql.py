from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from backend.capability_v2.schema_diff import SchemaDiff
from backend.capability_v2.schema_model import ColumnSpec, ExpectedSchema, IndexSpec, TableSpec


class SchemaPlanError(RuntimeError):
    pass


EXPORT_SQL = """-- Read-only structural export for DBeaver. Target: `ai00_test`.
SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE, TABLE_COLLATION, TABLE_TYPE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'ai00_test'
ORDER BY TABLE_NAME;

SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION,
       CASE WHEN COLUMN_DEFAULT IS NULL THEN '<SQL_NULL>' ELSE COLUMN_DEFAULT END AS COLUMN_DEFAULT,
       IS_NULLABLE, DATA_TYPE, COLUMN_TYPE, COLUMN_KEY, EXTRA,
       CHARACTER_SET_NAME, COLLATION_NAME, GENERATION_EXPRESSION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'ai00_test'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX,
       COLUMN_NAME, CASE WHEN SUB_PART IS NULL THEN '<SQL_NULL>' ELSE CAST(SUB_PART AS CHAR) END AS SUB_PART,
       INDEX_TYPE, COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'ai00_test'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
"""

PREFLIGHT_SQL = """-- STOP unless every result below matches the checklist. Target: `ai00_test`.
SELECT DATABASE() AS current_database, CURRENT_USER() AS connected_principal,
       VERSION() AS server_version, @@version_comment AS version_comment,
       @@sql_mode AS sql_mode;
SELECT DATABASE() = 'ai00_test' AS database_ok,
       INET_ATON(REGEXP_SUBSTR(VERSION(), '^[0-9]+\\.[0-9]+\\.[0-9]+')) >= INET_ATON('4.3.5') AS minimum_version_ok,
       LOCATE('OceanBase', @@version_comment) > 0 AS oceanbase_ok;
SELECT PRIVILEGE_TYPE, IS_GRANTABLE, PRIVILEGE_SCOPE
FROM (
  SELECT PRIVILEGE_TYPE, IS_GRANTABLE, 'GLOBAL' AS PRIVILEGE_SCOPE
  FROM information_schema.USER_PRIVILEGES
  WHERE GRANTEE = CONCAT("'", SUBSTRING_INDEX(CURRENT_USER(), '@', 1), "'@'", SUBSTRING_INDEX(CURRENT_USER(), '@', -1), "'")
    AND PRIVILEGE_TYPE IN ('CREATE', 'ALTER', 'INDEX')
  UNION ALL
  SELECT PRIVILEGE_TYPE, IS_GRANTABLE, 'DATABASE' AS PRIVILEGE_SCOPE
  FROM information_schema.SCHEMA_PRIVILEGES
  WHERE GRANTEE = CONCAT("'", SUBSTRING_INDEX(CURRENT_USER(), '@', 1), "'@'", SUBSTRING_INDEX(CURRENT_USER(), '@', -1), "'")
    AND TABLE_SCHEMA = 'ai00_test'
    AND PRIVILEGE_TYPE IN ('CREATE', 'ALTER', 'INDEX')
) AS DDL_PRIVILEGES
ORDER BY PRIVILEGE_TYPE, PRIVILEGE_SCOPE;
"""


def _quote(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", value):
        raise SchemaPlanError(f"unsafe_identifier:{value}")
    return "`" + value + "`"


def _default(value: str) -> str:
    scalar = re.fullmatch(
        r"\(\s*((?:'(?:''|[^'])*')|(?:[-+]?\d+(?:\.\d+)?)|NULL|TRUE|FALSE|"
        r"CURRENT_(?:DATE|TIME|TIMESTAMP)(?:\(\d*\))?)\s*\)",
        value,
        re.I,
    )
    return scalar.group(1) if scalar else value


def _index_column(value: str) -> str:
    match = re.fullmatch(r"([^()]+)\((\d+)\)", value)
    return _quote(match.group(1) if match else value) + (f"({match.group(2)})" if match else "")


def _column(column: ColumnSpec) -> str:
    result = f"{_quote(column.name)} {column.data_type} {'NULL' if column.nullable else 'NOT NULL'}"
    if column.default is not None: result += f" DEFAULT {_default(column.default)}"
    if column.extra: result += " " + column.extra
    return result


def _index(index: IndexSpec, *, alter=False) -> str:
    columns = ", ".join(_index_column(value) for value in index.columns)
    if index.primary: return f"PRIMARY KEY ({columns})"
    prefix = "UNIQUE " if index.unique else ""
    return f"{prefix}INDEX {_quote(index.name)} ({columns})"


def _table(table: TableSpec) -> str:
    definitions = [_column(column) for column in table.columns]
    definitions.extend(_index(index) for index in table.indexes)
    for constraint in table.constraints:
        if constraint.kind == "foreign_key":
            definitions.append(f"CONSTRAINT {_quote(constraint.name)} FOREIGN KEY (" +
                ", ".join(_quote(value) for value in constraint.columns) + ") REFERENCES " +
                _quote(constraint.referenced_table or "") + " (" +
                ", ".join(_quote(value) for value in constraint.referenced_columns) + ")")
        elif constraint.kind == "check":
            definitions.append(f"CONSTRAINT {_quote(constraint.name)} CHECK ({constraint.expression})")
    body = ",\n  ".join(definitions)
    return f"CREATE TABLE IF NOT EXISTS {_quote(table.name)} (\n  {body}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write(path: Path, content: bytes):
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream: stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _checklist(diff: SchemaDiff | None, export_only: bool) -> str:
    if export_only:
        return "# Schema export checklist\n\n1. In DBeaver select `ai00_test`.\n2. Run `00-export-schema.sql`.\n3. Export the three result sets using the exact CSV names.\n"
    manual = len(diff.manual) if diff else 0
    return ("# Single-database schema execution checklist\n\n"
        f"- Expected database: `ai00_test`\n- Manual findings: {manual}\n"
        "- Stop immediately when manual findings are non-zero.\n"
        "- Run `01`, `10`, `20`, `30`, then `90` in order; stop on the first error.\n"
        "- Export the three verification result sets and require a zero diff.\n")


def build_execution_package(*, expected: ExpectedSchema, diff: SchemaDiff | None,
                            output: Path, export_only: bool = False) -> tuple[Path, ...]:
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    if expected.database_name != "ai00_test" or (diff and diff.expected_sha256 != expected.schema_sha256):
        raise SchemaPlanError("expected_schema_identity_mismatch")
    documents: dict[str, bytes] = {
        "00-export-schema.sql": EXPORT_SQL.encode(),
        "expected-schema.json": _json(expected.to_dict()),
        "execution-checklist.md": _checklist(diff, export_only).encode(),
    }
    if not export_only:
        if diff is None: raise SchemaPlanError("snapshot_diff_required")
        documents["schema-diff.json"] = _json(diff.to_dict())
        if diff.manual:
            for name, content in documents.items(): _write(output / name, content)
            raise SchemaPlanError("manual_review_required")
        missing_tables, missing_columns, missing_indexes = [], [], []
        for item in diff.safe:
            if item.kind == "missing_table": missing_tables.append(_table(item.expected_object))
            elif item.kind in {"missing_nullable_column", "missing_defaulted_column"}:
                missing_columns.append(f"ALTER TABLE {_quote(item.table)} ADD COLUMN {_column(item.expected_object)};")
            elif item.kind == "missing_index":
                missing_indexes.append(f"ALTER TABLE {_quote(item.table)} ADD {_index(item.expected_object)};")
            else: raise SchemaPlanError(f"unsupported_safe_difference:{item.kind}")
        banner = f"-- Expected {expected.schema_sha256}; target `ai00_test`.\nUSE `ai00_test`;\n"
        documents.update({
            "01-preflight.sql": PREFLIGHT_SQL.encode(),
            "10-create-missing-tables.sql": (banner + "\n\n".join(missing_tables) + "\n").encode(),
            "20-add-safe-columns.sql": (banner + "\n".join(missing_columns) + "\n").encode(),
            "30-add-missing-indexes.sql": (banner + "\n".join(missing_indexes) + "\n").encode(),
            "90-verify-schema.sql": EXPORT_SQL.encode(),
        })
    forbidden = re.compile(r"\b(DROP|TRUNCATE|DELETE|RENAME)\b", re.I)
    if any(name.endswith(".sql") and forbidden.search(content.decode()) for name, content in documents.items()):
        raise SchemaPlanError("destructive_sql_detected")
    allowed = set(documents) | {"SHA256SUMS"}
    unexpected = {path.name for path in output.iterdir()} - allowed
    if unexpected: raise SchemaPlanError("unexpected_output_files:" + ",".join(sorted(unexpected)))
    sums = "".join(f"{hashlib.sha256(content).hexdigest()}  {name}\n" for name, content in sorted(documents.items()))
    documents["SHA256SUMS"] = sums.encode()
    for name, content in documents.items(): _write(output / name, content)
    return tuple(output / name for name in sorted(documents))
