from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

from backend.capability_v2.schema_model import (
    ColumnSpec, ConstraintSpec, ExpectedSchema, IndexSpec, TableSpec,
)
from backend.db.versioned_migrations import (
    MigrationError, _status_check_replacement, normalize_oceanbase_sql,
    prepare_resumable_statement, split_sql, strip_sql_comments,
)


class SchemaCompileError(RuntimeError):
    pass


IDENT = r"`?([A-Za-z_][A-Za-z0-9_$]*)`?"


@dataclass
class _Table:
    name: str
    owner: str
    runtime_domain: str
    legacy_name: bool
    columns: list[ColumnSpec] = field(default_factory=list)
    indexes: dict[str, IndexSpec] = field(default_factory=dict)
    constraints: dict[str, ConstraintSpec] = field(default_factory=dict)
    sources: set[str] = field(default_factory=set)


class _CompiledCheckMetadata:
    """Supply projected CHECK metadata to the authoritative migration guard."""

    def __init__(self, table: _Table):
        self.table = table

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, query, params):
        if "information_schema.CHECK_CONSTRAINTS" not in query:
            raise SchemaCompileError("unsupported_compiler_metadata_query")

    def fetchall(self):
        return [(item.name, item.expression) for item in self.table.constraints.values()
                if item.kind == "check"]


def _parts(text: str) -> list[str]:
    result, current = [], []
    depth = 0
    quote = None
    i = 0
    while i < len(text):
        char = text[i]
        if quote:
            current.append(char)
            if char == "\\" and i + 1 < len(text):
                i += 1; current.append(text[i])
            elif char == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 1; current.append(text[i])
                else:
                    quote = None
        elif char in "'\"`": quote = char; current.append(char)
        elif char == "(": depth += 1; current.append(char)
        elif char == ")": depth -= 1; current.append(char)
        elif char == "," and depth == 0:
            result.append("".join(current).strip()); current = []
        else: current.append(char)
        i += 1
    if current or text.strip(): result.append("".join(current).strip())
    return [item for item in result if item]


def _identifier(raw: str, source: str) -> str:
    raw = raw.strip().replace("`", "")
    if "." in raw:
        raise SchemaCompileError(f"cross_database_reference:{source}:1:{raw}")
    return raw.lower()


def _index_columns(raw: str) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+(ASC|DESC)$", "", item.strip(), flags=re.I).replace("`", "")
                 for item in _parts(raw))


def _normalize_data_type(value: str) -> str:
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(value):
        char = value[index]
        result.append(char if quote else char.upper())
        if quote:
            if char == "\\" and index + 1 < len(value):
                index += 1
                result.append(value[index])
            elif char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 1
                    result.append(value[index])
                else:
                    quote = None
        elif char in "'\"":
            quote = char
        index += 1
    return "".join(result)


def _top_level_syntax(value: str) -> str:
    """Mask literals and parenthesized expressions without moving SQL offsets."""
    result = list(value)
    depth, quote, index = 0, None, 0
    while index < len(value):
        char = value[index]
        if quote:
            result[index] = " "
            if char == "\\" and index + 1 < len(value):
                index += 1
                result[index] = " "
            elif char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 1
                    result[index] = " "
                else:
                    quote = None
        elif char in "'\"`":
            quote = char
            result[index] = " "
        elif char == "(":
            depth += 1
            result[index] = " "
        elif char == ")":
            depth -= 1
            result[index] = " "
        elif depth:
            result[index] = " "
        index += 1
    if quote or depth:
        raise SchemaCompileError("unbalanced_column_definition")
    return "".join(result)


def _column(definition: str, source: str) -> ColumnSpec:
    match = re.match(rf"^\s*{IDENT}\s+(.+)$", definition, re.S)
    if not match:
        raise SchemaCompileError(f"unsupported_column:{source}:1")
    name, tail = match.group(1).lower(), match.group(2).strip()
    keyword = re.search(
        r"\b(?:NOT\s+NULL|NULL\b|DEFAULT\b|AUTO_INCREMENT\b|PRIMARY\s+KEY|UNIQUE\b|COMMENT\b|COLLATE\b|CHARACTER\s+SET|ON\s+UPDATE|GENERATED\b|REFERENCES\b|AFTER\b|FIRST\b)",
        _top_level_syntax(tail), re.I,
    )
    data_type = _normalize_data_type((tail[:keyword.start()] if keyword else tail).strip())
    attrs = tail[keyword.start():].strip() if keyword else ""
    syntax = _top_level_syntax(attrs)
    nullable = not bool(re.search(r"\bNOT\s+NULL\b", syntax, re.I))
    default = None
    default_keyword = re.search(r"\bDEFAULT\b", syntax, re.I)
    default_match = re.match(
        r"\bDEFAULT\s+((?:'(?:''|\\.|[^'])*')|(?:\"(?:\"\"|\\.|[^\"])*\")|(?:\([^)]*\))|(?:[^\s,]+))",
        attrs[default_keyword.start():], re.I,
    ) if default_keyword else None
    if default_match: default = default_match.group(1)
    extra = []
    if re.search(r"\bAUTO_INCREMENT\b", syntax, re.I): extra.append("AUTO_INCREMENT")
    update_keyword = re.search(r"\bON\s+UPDATE\b", syntax, re.I)
    update = re.match(r"\bON\s+UPDATE\s+([^\s,]+(?:\([^)]*\))?)", attrs[update_keyword.start():], re.I) if update_keyword else None
    if update: extra.append("ON UPDATE " + update.group(1).upper())
    generation_expression = None
    generated = re.search(r"\bGENERATED\s+(?:ALWAYS\s+)?AS\b", syntax, re.I)
    if generated:
        expression_start = generated.end()
        expression_end = re.search(r"\S", syntax[expression_start:])
        expression_end = expression_start + expression_end.start() if expression_end else len(attrs)
        expression = attrs[expression_start:expression_end].strip()
        if not (expression.startswith("(") and expression.endswith(")")):
            raise SchemaCompileError(f"unsupported_generated_column:{source}:1")
        generation_expression = expression[1:-1].strip()
        storage = re.match(r"(STORED|VIRTUAL)\b", syntax[expression_end:], re.I)
        extra.append((storage.group(1).upper() if storage else "VIRTUAL") + " GENERATED")
    return ColumnSpec(name, data_type, nullable, default, " ".join(extra), (source,), generation_expression)


def _merge_column(table: _Table, column: ColumnSpec, source: str, *, replace_existing=False):
    for position, existing in enumerate(table.columns):
        if existing.name != column.name: continue
        if replace_existing:
            table.columns[position] = column; return
        if existing.structural_key() != column.structural_key():
            raise SchemaCompileError(f"column_conflict:{table.name}.{column.name}:{source}:1")
        table.columns[position] = replace(existing, sources=tuple(sorted(set(existing.sources + column.sources))))
        return
    table.columns.append(column)


def _merge_index(table: _Table, index: IndexSpec, source: str):
    existing = table.indexes.get(index.name)
    if existing and existing.structural_key() != index.structural_key():
        raise SchemaCompileError(f"index_conflict:{table.name}.{index.name}:{source}:1")
    table.indexes[index.name] = replace(
        existing or index,
        sources=tuple(sorted(set((existing.sources if existing else ()) + index.sources))),
    )


def _unnamed_index_name(table: _Table, column: str) -> str:
    match = re.match(IDENT, column)
    if not match:
        raise SchemaCompileError(f"unsupported_unnamed_index:{table.name}:{column}")
    base = match.group(1)
    name, suffix = base, 2
    while name.lower() in {existing.lower() for existing in table.indexes}:
        name = f"{base}_{suffix}"
        suffix += 1
    return name


def _table_item(table: _Table, item: str, source: str):
    constraint_name = None
    constrained = re.match(rf"^CONSTRAINT\s+{IDENT}\s+(.+)$", item, re.I | re.S)
    if constrained: constraint_name, item = constrained.group(1), constrained.group(2)
    primary = re.match(r"^PRIMARY\s+KEY\s*\((.+)\)", item, re.I | re.S)
    index = re.fullmatch(rf"^(?:(UNIQUE)\s*(?:(?:KEY|INDEX)\s*)?|(?:KEY|INDEX)\s*)(?:{IDENT}\s*)?\((.+)\)", item, re.I | re.S)
    foreign = re.match(rf"^FOREIGN\s+KEY\s*\((.+?)\)\s+REFERENCES\s+([^\s(]+)\s*\((.+?)\)", item, re.I | re.S)
    check = re.match(r"^CHECK\s*\((.+)\)$", item, re.I | re.S)
    if primary:
        _merge_index(table, IndexSpec("PRIMARY", _index_columns(primary.group(1)), True, True, (source,)), source)
    elif index:
        columns = _index_columns(index.group(3))
        name = index.group(2) or constraint_name or _unnamed_index_name(table, columns[0])
        _merge_index(table, IndexSpec(name, columns, bool(index.group(1)), False, (source,)), source)
    elif foreign:
        name = constraint_name or f"fk_{table.name}_{len(table.constraints)+1}"
        table.constraints[name] = ConstraintSpec(name, "foreign_key", _index_columns(foreign.group(1)),
            _identifier(foreign.group(2), source), _index_columns(foreign.group(3)), sources=(source,))
    elif check:
        name = constraint_name or f"check_{table.name}_{len(table.constraints)+1}"
        table.constraints[name] = ConstraintSpec(name, "check", expression=check.group(1).strip(), sources=(source,))
    else:
        if constraint_name or re.match(r"^(?:UNIQUE|KEY|INDEX|PRIMARY|FOREIGN|CHECK|FULLTEXT|SPATIAL)\b", item, re.I):
            raise SchemaCompileError(f"unsupported_table_item:{source}:1:{item[:40]}")
        column = _column(item, source)
        _merge_column(table, column, source)
        if re.search(r"\bPRIMARY\s+KEY\b", _top_level_syntax(item), re.I):
            _merge_index(table, IndexSpec("PRIMARY", (column.name,), True, True, (source,)), source)
        if re.search(r"\bUNIQUE\b", _top_level_syntax(item), re.I):
            _merge_index(table, IndexSpec(_unnamed_index_name(table, column.name), (column.name,), True, False, (source,)), source)


def _resolve_files(root: Path, paths: list[str]) -> list[Path]:
    files = set()
    for relative in paths:
        path = root / relative
        if not path.exists(): raise SchemaCompileError(f"missing_schema_path:{relative}")
        files.update(path.rglob("*.sql") if path.is_dir() else [path])
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def compile_expected_schema(root: Path) -> ExpectedSchema:
    root = Path(root).resolve()
    manifests = json.loads((root / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    ownership_doc = json.loads((root / "backend/governance/domain_table_ownership.json").read_text(encoding="utf-8"))
    ownership = {row["table"]: row for row in ownership_doc["tables"]}
    profile = json.loads((root / "backend/capability_v2/database_profiles/single_database.json").read_text(encoding="utf-8"))
    path_domains: dict[str, str] = {}
    for domain in manifests["domains"]:
        for schema_path in domain["database"].get("schema_paths", []):
            other = path_domains.setdefault(schema_path, domain["domain_id"])
            if other != domain["domain_id"]: raise SchemaCompileError(f"schema_path_conflict:{schema_path}")
    baseline = profile.get("baseline_schema_path")
    files = _resolve_files(root, ([baseline] if baseline else []) + list(path_domains))
    files.sort(key=lambda path: (0 if baseline and path == root / baseline else 1, path.relative_to(root).as_posix()))
    tables: dict[str, _Table] = {}
    for path in files:
        source = path.relative_to(root).as_posix()
        claimed = next((domain for prefix, domain in path_domains.items()
                        if path == root / prefix or (root / prefix).is_dir() and path.is_relative_to(root / prefix)), None)
        sql = normalize_oceanbase_sql(path.read_text(encoding="utf-8"))
        for raw in split_sql(sql):
            statement = strip_sql_comments(raw).strip()
            if not statement: continue
            if baseline and path == root / baseline and re.match(
                r"^(CREATE\s+DATABASE|USE\s+|SET\s+|INSERT\s+IGNORE\s+INTO\s+)", statement, re.I
            ):
                continue
            # Backfill DML is validated by the migration and domain-ownership
            # gates; it does not contribute to the expected DDL projection.
            if re.match(r"^(INSERT|UPDATE|DELETE)\b", statement, re.I):
                continue
            if re.match(r"^(DROP|RENAME|TRUNCATE)\b", statement, re.I):
                raise SchemaCompileError(f"destructive_ddl:{source}:1")
            create = re.match(r"^CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?([^\s(]+)\s*\((.*)\)\s*(?:ENGINE\b.*)?$", statement, re.I | re.S)
            alter = re.match(r"^ALTER\s+TABLE\s+([^\s]+)\s+(.+)$", statement, re.I | re.S)
            create_index = re.match(r"^CREATE\s+(UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s]+)\s+ON\s+([^\s(]+)\s*\((.+)\)$", statement, re.I | re.S)
            create_trigger = re.match(r"^CREATE\s+TRIGGER\s+[^\s]+\s+BEFORE\s+(?:UPDATE|DELETE)\s+ON\s+([^\s]+)\b", statement, re.I | re.S)
            if create:
                name = _identifier(create.group(2), source)
                row = ownership.get(name)
                if not row: raise SchemaCompileError(f"unowned_table:{name}:{source}:1")
                # Historical top-level migrations can contain tables from more than
                # one domain. New domain-local migration directories are strict.
                if "/domains/" in source and claimed and row["owner"] != claimed:
                    raise SchemaCompileError(f"cross_domain_table:{claimed}:{name}:{source}:1")
                already_exists = name in tables
                table = tables.setdefault(name, _Table(name, row["owner"], row["runtime_domain"], row["legacy_name"]))
                table.sources.add(source)
                if already_exists and create.group(1):
                    continue
                for item in _parts(create.group(3)): _table_item(table, item, source)
            elif alter:
                name = _identifier(alter.group(1), source)
                if name not in tables: raise SchemaCompileError(f"alter_before_create:{name}:{source}:1")
                table = tables[name]; table.sources.add(source)
                replacement = _status_check_replacement(raw)
                if replacement:
                    try:
                        prepared = prepare_resumable_statement(_CompiledCheckMetadata(table), raw)
                    except MigrationError as exc:
                        raise SchemaCompileError(f"invalid_status_check_replacement:{source}:1:{exc}") from exc
                    if prepared is None:
                        continue
                    if replacement[0] == "retire":
                        # The placeholder denotes the old expression, not its generated name.
                        retired = re.fullmatch(r"ALTER TABLE `[^`]+` DROP CHECK `([^`]+)`", prepared)
                        if not retired:
                            raise SchemaCompileError(f"unsupported_status_check_retirement:{source}:1")
                        del table.constraints[retired.group(1)]
                        continue
                    # Keep the logical ADD name; physical names depend on runtime prefix.
                for action in _parts(alter.group(2)):
                    drop_primary = re.match(r"^DROP\s+PRIMARY\s+KEY$", action, re.I)
                    add_primary = re.match(r"^ADD\s+PRIMARY\s+KEY\s*\((.+)\)$", action, re.I | re.S)
                    add_column = re.match(r"^ADD\s+(?:COLUMN\s+)?(IF\s+NOT\s+EXISTS\s+)?(.+)$", action, re.I | re.S)
                    modify = re.match(r"^MODIFY\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?(.+)$", action, re.I | re.S)
                    change = re.match(rf"^CHANGE\s+(?:COLUMN\s+)?{IDENT}\s+{IDENT}\s+(.+)$", action, re.I | re.S)
                    add_index = re.match(rf"^ADD\s+(UNIQUE\s+)?(?:KEY|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?{IDENT}\s*\((.+)\)$", action, re.I | re.S)
                    add_constraint = re.match(r"^ADD\s+((?:CONSTRAINT\s+|CHECK\s*\(|FOREIGN\s+KEY\b|UNIQUE\b|KEY\b|INDEX\b|FULLTEXT\b|SPATIAL\b).+)$", action, re.I | re.S)
                    if drop_primary:
                        table.indexes.pop("PRIMARY", None)
                    elif add_primary:
                        table.indexes["PRIMARY"] = IndexSpec(
                            "PRIMARY", _index_columns(add_primary.group(1)), True, True, (source,)
                        )
                    elif add_index:
                        _merge_index(table, IndexSpec(add_index.group(2), _index_columns(add_index.group(3)), bool(add_index.group(1)), False, (source,)), source)
                    elif add_constraint:
                        _table_item(table, add_constraint.group(1), source)
                    elif add_column:
                        column = _column(add_column.group(2), source)
                        if add_column.group(1) and any(item.name == column.name for item in table.columns):
                            continue
                        _table_item(table, add_column.group(2), source)
                    elif modify:
                        _merge_column(table, _column(modify.group(1), source), source, replace_existing=True)
                    elif change:
                        if change.group(1).lower() != change.group(2).lower():
                            raise SchemaCompileError(f"column_rename_forbidden:{source}:1")
                        _merge_column(table, _column(f"{change.group(2)} {change.group(3)}", source), source, replace_existing=True)
                    else: raise SchemaCompileError(f"unsupported_alter:{source}:1:{action[:40]}")
            elif create_index:
                name = _identifier(create_index.group(3), source)
                if name not in tables: raise SchemaCompileError(f"index_before_create:{name}:{source}:1")
                table = tables[name]; table.sources.add(source)
                _merge_index(table, IndexSpec(create_index.group(2).replace("`", ""), _index_columns(create_index.group(4)), bool(create_index.group(1)), False, (source,)), source)
            elif create_trigger:
                name = _identifier(create_trigger.group(1), source)
                if name not in tables: raise SchemaCompileError(f"trigger_before_create:{name}:{source}:1")
                tables[name].sources.add(source)
            else:
                raise SchemaCompileError(f"unsupported_ddl:{source}:1:{statement[:40]}")
    for table in tables.values():
        primary = table.indexes.get("PRIMARY")
        if primary:
            primary_columns = set(primary.columns)
            table.columns = [
                replace(column, nullable=False) if column.name in primary_columns else column
                for column in table.columns
            ]
        for constraint in table.constraints.values():
            if constraint.referenced_table and constraint.referenced_table in ownership:
                if ownership[constraint.referenced_table]["owner"] != table.owner:
                    raise SchemaCompileError(f"cross_domain_foreign_key:{table.name}:{constraint.name}")
    frozen = tuple(TableSpec(
        item.name, item.owner, item.runtime_domain, item.legacy_name,
        tuple(item.columns), tuple(sorted(item.indexes.values(), key=lambda value: value.name)),
        tuple(sorted(item.constraints.values(), key=lambda value: value.name)), tuple(sorted(item.sources)),
    ) for item in sorted(tables.values(), key=lambda value: value.name))
    return ExpectedSchema(
        frozen,
        isolation_profile=profile["isolation_profile"],
        database_name=profile["database_name"],
    )
