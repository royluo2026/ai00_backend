"""OceanBase MySQL-mode compatibility checks shared by migrations and deploy tooling."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MIN_OCEANBASE_VERSION = (4, 3, 5)
MIN_OCEANBASE_VERSION_TEXT = ".".join(map(str, MIN_OCEANBASE_VERSION))

_LOB_TYPES = {"TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT", "TINYBLOB", "BLOB", "MEDIUMBLOB", "LONGBLOB", "JSON"}
_POSTGRES_PATTERNS = (
    ("OB001", re.compile(r"::\s*[A-Za-z_]", re.I), "PostgreSQL cast syntax (::type)"),
    ("OB002", re.compile(r"\bILIKE\b", re.I), "ILIKE"),
    ("OB003", re.compile(r"\bJSONB\b", re.I), "JSONB"),
    ("OB004", re.compile(r"\bON\s+CONFLICT\b", re.I), "ON CONFLICT"),
    ("OB005", re.compile(r"\bRETURNING\b", re.I), "RETURNING"),
    ("OB006", re.compile(r"\b(?:BIG)?SERIAL\b", re.I), "SERIAL/BIGSERIAL"),
    ("OB007", re.compile(r"\bNULLS\s+(?:FIRST|LAST)\b", re.I), "NULLS FIRST/LAST"),
)


@dataclass(frozen=True)
class CompatibilityIssue:
    code: str
    path: str
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), sql, flags=re.S)
    return re.sub(r"(?m)--[^\n]*|#[^\n]*", "", sql)


def _split_top_level(value: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    i = 0
    while i < len(value):
        char = value[i]
        nxt = value[i + 1] if i + 1 < len(value) else ""
        if quote:
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
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "," and depth == 0:
            chunks.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    if current:
        chunks.append("".join(current))
    return chunks


def _column_fragments(sql: str) -> Iterable[tuple[str, str, int]]:
    """Yield (column name, definition, line) for CREATE/ALTER column definitions."""
    cleaned = _strip_comments(sql)
    # CREATE TABLE bodies. Migration files intentionally avoid stored programs.
    for match in re.finditer(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?[\w]+`?\s*\(", cleaned, re.I):
        start = match.end()
        depth = 1
        quote: str | None = None
        i = start
        while i < len(cleaned) and depth:
            char = cleaned[i]
            nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""
            if quote:
                if char == "\\" and nxt:
                    i += 1
                elif char == quote:
                    if nxt == quote:
                        i += 1
                    else:
                        quote = None
            elif char in ("'", '"', "`"):
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            i += 1
        body = cleaned[start : i - 1]
        body_offset = cleaned.count("\n", 0, start) + 1
        consumed = 0
        for fragment in _split_top_level(body):
            col = re.match(r"\s*`?([A-Za-z_][\w]*)`?\s+([A-Za-z]+)\b", fragment)
            if col and col.group(1).upper() not in {"PRIMARY", "UNIQUE", "KEY", "INDEX", "CONSTRAINT", "FOREIGN", "CHECK"}:
                line = body_offset + body.count("\n", 0, consumed)
                yield col.group(1), fragment[col.start(2) :], line
            consumed += len(fragment) + 1
    for match in re.finditer(
        r"\bALTER\s+TABLE\s+`?[\w]+`?\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z_][\w]*)`?\s+([^;]+)",
        cleaned,
        re.I,
    ):
        yield match.group(1), match.group(2), cleaned.count("\n", 0, match.start()) + 1


def text_columns_with_defaults(sql: str) -> list[str]:
    result: list[str] = []
    for name, definition, _line in _column_fragments(sql):
        type_match = re.match(r"\s*([A-Za-z]+)\b", definition)
        if type_match and type_match.group(1).upper() in _LOB_TYPES and re.search(r"\bDEFAULT\b", definition, re.I):
            result.append(name)
    return result


def audit_sql(path: Path, sql: str, *, check_postgres: bool = True) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    cleaned = _strip_comments(sql)
    if check_postgres:
        for code, pattern, label in _POSTGRES_PATTERNS:
            for match in pattern.finditer(cleaned):
                issues.append(CompatibilityIssue(code, str(path), cleaned.count("\n", 0, match.start()) + 1, f"unsupported MySQL-mode syntax: {label}"))
    for name, definition, line in _column_fragments(sql):
        type_match = re.match(r"\s*([A-Za-z]+)\b", definition)
        if type_match and type_match.group(1).upper() in _LOB_TYPES and re.search(r"\bDEFAULT\b", definition, re.I):
            issues.append(CompatibilityIssue("OB010", str(path), line, f"{type_match.group(1).upper()} column {name!r} cannot declare DEFAULT in OceanBase MySQL mode"))
    for match in re.finditer(r"\b(?:CREATE\s+(?:UNIQUE\s+)?INDEX(?:\s+IF\s+NOT\s+EXISTS)?|(?:UNIQUE\s+)?(?:KEY|INDEX))\s+`?([A-Za-z_][\w]*)`?", cleaned, re.I):
        name = match.group(1)
        if len(name.encode("utf-8")) > 64:
            issues.append(CompatibilityIssue("OB011", str(path), cleaned.count("\n", 0, match.start()) + 1, f"index name exceeds 64 bytes: {name}"))
    return issues


def parse_oceanbase_version(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?:OceanBase[^0-9]*)?(\d+)\.(\d+)\.(\d+)", value, re.I)
    return tuple(map(int, match.groups())) if match else None


def assert_supported_server(version_text: str, compatibility_mode: str) -> None:
    if compatibility_mode.strip().upper() != "MYSQL":
        raise RuntimeError(f"OceanBase compatibility mode must be MYSQL, got {compatibility_mode!r}")
    version = parse_oceanbase_version(version_text)
    if version is None:
        raise RuntimeError(f"cannot parse OceanBase version: {version_text!r}")
    if version < MIN_OCEANBASE_VERSION:
        raise RuntimeError(
            f"OceanBase {MIN_OCEANBASE_VERSION_TEXT}+ is required; server reports {version_text!r}"
        )

def _server_value(row, preferred: str | None = None):
    if isinstance(row, dict):
        if preferred and preferred in row:
            return row[preferred]
        return list(row.values())[-1]
    return row[-1]


def verify_live_server(conn) -> dict[str, str]:
    """Verify the minimum OceanBase MySQL-mode and strict SQL-mode contract."""
    with conn.cursor() as cur:
        cur.execute("SELECT VERSION() AS version")
        version = str(_server_value(cur.fetchone(), "version"))
        cur.execute("SHOW VARIABLES LIKE 'ob_compatibility_mode'")
        mode_row = cur.fetchone()
        if not mode_row:
            raise RuntimeError(
                "server does not expose ob_compatibility_mode; verify this is OceanBase"
            )
        mode = str(_server_value(mode_row, "Value"))
        cur.execute("SELECT @@sql_mode AS sql_mode")
        sql_mode = str(_server_value(cur.fetchone(), "sql_mode"))
    assert_supported_server(version, mode)
    modes = {item.strip().upper() for item in sql_mode.split(",") if item.strip()}
    if not ({"STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"} & modes):
        raise RuntimeError(
            "OceanBase sql_mode must enable STRICT_TRANS_TABLES or STRICT_ALL_TABLES"
        )
    return {"version": version, "compatibility_mode": mode, "sql_mode": sql_mode}