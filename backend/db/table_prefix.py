"""Runtime SQL table-prefix rewriting for shared test databases."""
from __future__ import annotations

import logging
import os
import re
import socket
from urllib.parse import urlsplit

_log = logging.getLogger("backend.db.table_prefix")

_PREFIX = ""
_LEDGER = re.compile(r"ai00_[a-z0-9_]+_schema_migrations\Z")
_TRIGGERS = {"base_historical_uploads_no_update", "base_historical_uploads_no_delete"}
_PRODUCTION_URL = "https://workmanship-backend.chehejia.com"
REMOTE_BACKEND_ORIGINS = frozenset({
    _PRODUCTION_URL, "https://workmanship-backend-test.chehejia.com",
})


def is_local_test_backend_url(public_url: str) -> bool:
    try:
        parsed = urlsplit(public_url.strip())
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme in {"http", "https"} and port == 8080
            and parsed.hostname in {"127.0.0.1", "localhost", socket.gethostname().lower()}
            and not parsed.username and not parsed.password and parsed.path in {"", "/"}
            and not parsed.query and not parsed.fragment)


def validate_runtime_profile(profile: str, prefix: str, public_url: str) -> None:
    normalized_url = public_url.strip().rstrip("/")
    if (not profile and not os.getenv("ENV_FILE") and os.getenv("AI00_ALLOW_DATA_ENVIRONMENT_SWITCH") == "1"
            and os.getenv("AI00_DATA_ENVIRONMENT_STATE_FILE") and is_local_test_backend_url(public_url)):
        if prefix not in {"test_", "pp_", ""}:
            raise ValueError("unsupported table prefix")
        return
    if profile not in {"", "test", "production"}:
        raise ValueError("unsupported runtime profile")
    if profile == "production":
        if prefix != "pp_" or normalized_url not in REMOTE_BACKEND_ORIGINS:
            raise ValueError("production profile requires pp_ and the production backend URL")
        return
    if prefix == "pp_":
        raise ValueError("pp_ requires an explicit production profile")
    if prefix not in {"", "test_"}:
        raise ValueError("unsupported table prefix")
    if normalized_url in REMOTE_BACKEND_ORIGINS:
        raise ValueError("production backend URL requires an explicit production profile")
    if profile == "test":
        if prefix != "test_":
            raise ValueError("test profile requires test_ table prefix")
        if not is_local_test_backend_url(public_url):
            raise ValueError("test profile requires local backend URL on port 8080")


def _tokens(sql: str):
    position = 0
    while position < len(sql):
        start = position
        char = sql[position]
        if char.isspace():
            while position < len(sql) and sql[position].isspace():
                position += 1
            kind = "skip"
        elif char == "#" or (sql.startswith("--", position) and
                              (position + 2 == len(sql) or sql[position + 2].isspace())):
            end = sql.find("\n", position)
            position = len(sql) if end < 0 else end
            kind = "skip"
        elif sql.startswith("/*", position):
            if sql.startswith("/*!", position) or sql[position + 2:position + 4].upper() == "M!":
                raise ValueError("executable comment refused with table prefix")
            end = sql.find("*/", position + 2)
            position = len(sql) if end < 0 else end + 2
            kind = "skip"
        elif char in ("'", '"', "`"):
            position += 1
            while position < len(sql):
                if sql[position] == "\\" and position + 1 < len(sql):
                    position += 2
                elif sql[position] == char:
                    position += 1
                    if position < len(sql) and sql[position] == char:
                        position += 1
                    else:
                        break
                else:
                    position += 1
            kind = "identifier" if char == "`" else "skip"
        elif char.isalpha() or char == "_":
            position += 1
            while position < len(sql) and (sql[position].isalnum() or sql[position] == "_"):
                position += 1
            kind = "identifier"
        else:
            position += 1
            kind = "symbol"
        yield kind, sql[start:position]


def _identifier(text: str) -> str:
    return text[1:-1].replace("``", "`") if text.startswith("`") else text


def _next_significant(tokens, start: int):
    for index in range(start, len(tokens)):
        if tokens[index][0] != "skip":
            return tokens[index]
    return None


def _physical_table_identifier(name: str, prefix: str | None = None) -> str:
    active_prefix = _PREFIX if prefix is None else prefix
    folded = name.casefold()
    for other_prefix in ("test_", "pp_"):
        remainder = folded[len(other_prefix):] if folded.startswith(other_prefix) else ""
        if other_prefix != active_prefix and (remainder.startswith("workmanship_") or _LEDGER.fullmatch(remainder)):
            raise ValueError("cross-environment table reference refused")
    return active_prefix + name if folded.startswith("workmanship_") or _LEDGER.fullmatch(folded) else name


def configure_table_prefix(prefix: str) -> None:
    """Configure the prefix prepended to every ``workmanship_`` table name."""
    global _PREFIX
    normalized = (prefix or "").strip()
    if normalized and not re.fullmatch(r"[A-Za-z0-9_]+", normalized):
        raise ValueError("unsupported table prefix: invalid characters")
    if normalized not in {"", "test_", "pp_"}:
        raise ValueError("unsupported table prefix")
    _PREFIX = normalized
    if _PREFIX:
        _log.info("TABLE_PREFIX active: workmanship_ -> %sworkmanship_", _PREFIX)


def current_table_prefix() -> str:
    return _PREFIX


def rewrite_sql(sql: str, prefix: str | None = None) -> str:
    """Rewrite application table identifiers in SQL table positions only."""
    if prefix is not None and prefix not in {"", "test_", "pp_"}:
        raise ValueError("unsupported table prefix")
    active_prefix = _PREFIX if prefix is None else prefix
    if not active_prefix:
        return sql
    tokens = list(_tokens(sql))
    significant = [(kind, text) for kind, text in tokens if kind != "skip"]
    if len(significant) == 1 and significant[0][0] == "identifier":
        return _physical_table_identifier(_identifier(significant[0][1]), active_prefix)
    output = []
    depth = 0
    from_depths = set()
    expect_table = False
    expect_trigger = False
    trigger_definition = False
    index_definition = False
    previous_word = ""
    statement_command = ""
    ddl_table_list = ""
    create_like_next = False
    alter_rename_target = False
    update_table_list = False
    for index, (kind, text) in enumerate(tokens):
        if kind == "skip":
            if expect_table and text.startswith('"'):
                raise ValueError("double-quoted table identifier refused with table prefix")
            if expect_trigger and text.startswith('"'):
                raise ValueError("double-quoted trigger identifier refused with table prefix")
            output.append(text)
            continue
        if text == "(":
            depth += 1
            expect_table = False
        elif text == ")":
            from_depths.discard(depth)
            depth = max(0, depth - 1)
        elif text == ";":
            from_depths.clear()
            expect_table = False
            expect_trigger = False
            trigger_definition = False
            index_definition = False
            previous_word = ""
            statement_command = ""
            ddl_table_list = ""
            create_like_next = False
            alter_rename_target = False
            update_table_list = False
        elif text == "," and depth in from_depths:
            expect_table = True
        elif text == "," and depth == 0 and ddl_table_list:
            expect_table = True
        elif text == "," and depth == 0 and update_table_list:
            expect_table = True
        if kind == "identifier":
            name = _identifier(text)
            upper = name.upper()
            quoted = text.startswith("`")
            if not statement_command and not quoted:
                statement_command = upper
            if expect_trigger:
                if upper not in {"IF", "NOT", "EXISTS"}:
                    physical_name = prefixed_trigger_name(name, active_prefix)
                    text = f"`{physical_name}`" if quoted else physical_name
                    expect_trigger = False
                output.append(text)
                previous_word = upper
                continue
            if expect_table:
                if (quoted or upper not in {"IF", "NOT", "EXISTS", "ONLY", "TEMPORARY"}) and not (
                    (statement_command == "TRUNCATE" or statement_command == "LOAD") and upper == "TABLE"
                ):
                    next_token = _next_significant(tokens, index + 1)
                    if not next_token or next_token[1] != ".":
                        physical_name = _physical_table_identifier(name, active_prefix)
                        if physical_name != name:
                            name = physical_name
                            text = f"`{name}`" if text.startswith("`") else name
                        expect_table = False
                        if statement_command == "CREATE" and next_token and next_token[0] == "identifier" \
                                and _identifier(next_token[1]).upper() == "LIKE":
                            create_like_next = True
                        if index_definition:
                            index_definition = False
                    output.append(text)
                    previous_word = upper
                    continue
            if quoted:
                output.append(text)
                previous_word = ""
                continue
            if statement_command == "WITH" and depth == 0 and upper in {"SELECT", "INSERT", "REPLACE", "UPDATE", "DELETE"}:
                statement_command = upper
            if upper in {"WHERE", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION", "ON", "SET", "VALUES", "RETURNING"}:
                from_depths.discard(depth)
            if upper == "SET" and statement_command == "UPDATE" and depth == 0:
                update_table_list = False
            if upper == "INDEX":
                index_definition = True
            elif upper == "TRIGGER" and statement_command == "CREATE":
                expect_trigger = True
                trigger_definition = True
            elif upper == "TRUNCATE":
                expect_table = True
            elif upper in {"HANDLER", "DESCRIBE", "DESC"} and statement_command == upper:
                expect_table = True
            elif upper == "FROM":
                from_depths.add(depth)
                expect_table = True
            elif upper == "USING" and statement_command == "DELETE":
                from_depths.add(depth)
                expect_table = True
            elif upper == "TABLE" and statement_command in {"DROP", "RENAME"}:
                ddl_table_list = statement_command
                expect_table = True
            elif upper == "VIEW" and depth == 0 and (
                (statement_command == "CREATE" and previous_word in {"CREATE", "REPLACE"}) or
                (statement_command == "DROP" and previous_word == "DROP") or
                (statement_command == "SHOW" and previous_word == "CREATE")
            ):
                if statement_command == "DROP":
                    ddl_table_list = statement_command
                expect_table = True
            elif upper == "TABLES" and statement_command == "LOCK" and previous_word == "LOCK":
                ddl_table_list = statement_command
                expect_table = True
            elif upper == "ON" and trigger_definition:
                expect_table = True
                trigger_definition = False
            elif upper in {"JOIN", "INTO", "TABLE", "REFERENCES"}:
                expect_table = True
            elif upper == "UPDATE" and previous_word != "KEY" and not trigger_definition:
                expect_table = True
                if statement_command == "UPDATE":
                    update_table_list = True
            elif upper == "ON" and index_definition:
                expect_table = True
            elif upper == "TO" and ddl_table_list == "RENAME":
                expect_table = True
            elif upper == "RENAME" and statement_command == "ALTER":
                next_token = _next_significant(tokens, index + 1)
                alter_rename_target = bool(next_token and next_token[0] == "identifier" and
                                           _identifier(next_token[1]).upper() in {"TO", "AS"})
            elif upper in {"TO", "AS"} and alter_rename_target:
                expect_table = True
                alter_rename_target = False
            elif upper == "LIKE" and create_like_next:
                expect_table = True
                create_like_next = False
            previous_word = upper
        output.append(text)
    return "".join(output)


def physical_table_name(table: str) -> str:
    if _PREFIX:
        return _physical_table_identifier(table)
    return table


def logical_table_name(table: str) -> str | None:
    if not isinstance(table, str):
        return None
    if _PREFIX:
        physical_prefix = _PREFIX + "workmanship_"
        return table[len(_PREFIX):] if table.casefold().startswith(physical_prefix) else None
    return table if table.casefold().startswith("workmanship_") else None


def table_prefix_active() -> bool:
    return bool(_PREFIX)


def prefixed_trigger_name(name: str, prefix: str | None = None) -> str:
    active_prefix = _PREFIX if prefix is None else prefix
    folded = name.casefold()
    if active_prefix and folded in _TRIGGERS:
        return active_prefix + name
    if active_prefix and any(folded == other + trigger for other in {"test_", "pp_"} - {active_prefix} for trigger in _TRIGGERS):
        raise ValueError("cross-environment trigger reference refused")
    return name
