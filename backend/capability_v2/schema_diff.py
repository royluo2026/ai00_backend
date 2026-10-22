from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.capability_v2.schema_model import ColumnSpec, ExpectedSchema, IndexSpec, TableSpec
from backend.capability_v2.schema_snapshot import SchemaSnapshot, SnapshotColumn, SnapshotIndex


@dataclass(frozen=True)
class SchemaDifference:
    kind: str
    table: str
    object_name: str | None = None
    expected_value: object | None = None
    actual_value: object | None = None
    expected_object: object | None = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in {
            "kind": self.kind, "table": self.table, "object_name": self.object_name,
            "expected_value": self.expected_value, "actual_value": self.actual_value,
        }.items() if value is not None}


@dataclass(frozen=True)
class SchemaDiff:
    database_name: str
    expected_sha256: str
    safe: tuple[SchemaDifference, ...]
    manual: tuple[SchemaDifference, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1, "database_name": self.database_name,
            "expected_sha256": self.expected_sha256,
            "safe": [item.to_dict() for item in self.safe],
            "manual": [item.to_dict() for item in self.manual],
            "counts": {"safe": len(self.safe), "manual": len(self.manual)},
        }


def _uppercase_type_syntax(value: str) -> str:
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


def _type(value: str) -> str:
    result = _uppercase_type_syntax(re.sub(r"\s+", " ", value.strip()))
    result = re.sub(r"^INTEGER\b", "INT", result)
    result = re.sub(r"^(TINYINT|SMALLINT|MEDIUMINT|INT|BIGINT)\(\d+\)", r"\1", result)
    if result == "BOOLEAN":
        result = "TINYINT"
    return result


def _default(value: str | None, data_type: str | None = None) -> str | None:
    if value is None: return None
    result = value.strip()
    if result.upper() == "NULL": return None
    while result.startswith("(") and result.endswith(")"):
        result = result[1:-1].strip()
    if len(result) >= 2 and result[0] == result[-1] and result[0] in {"'", '"'}:
        result = result[1:-1]
    result = re.sub(r"^CURRENT_TIMESTAMP(?:\(\d+\))?$", "CURRENT_TIMESTAMP", result, flags=re.I)
    normalized_type = _type(data_type or "")
    if normalized_type in {"BOOLEAN", "TINYINT"}:
        if result.upper() == "FALSE": result = "0"
        if result.upper() == "TRUE": result = "1"
    if normalized_type.startswith(("DECIMAL", "NUMERIC", "FLOAT", "DOUBLE")):
        try:
            result = format(Decimal(result), "f")
            if "." in result:
                result = result.rstrip("0").rstrip(".") or "0"
        except InvalidOperation:
            pass
    return result


def _extra(value: str) -> str:
    return re.sub(r"\bDEFAULT_GENERATED\b", "", value.upper()).strip()


def _expression(value: str | None) -> tuple:
    """Compare SQL syntax conservatively, preserving literals and operator grouping."""
    tokens = re.findall(r"'(?:''|\\.|[^'])*'|\"(?:\"\"|\\.|[^\"])*\"|`(?:``|[^`])*`|[A-Za-z_][A-Za-z0-9_$]*|\d+(?:\.\d+)?|<>|!=|<=|>=|\S", value or "")
    tokens = tuple(token if token.startswith(("'", '"')) else token.strip("`").lower() for token in tokens)

    def normalize(items):
        if not items:
            return ()
        depth, top = 0, []
        for index, token in enumerate(items):
            if token == "(": depth += 1
            elif token == ")": depth -= 1
            if depth == 0: top.append(index)
        if items[0] == "(" and top == [len(items) - 1]:
            return normalize(items[1:-1])
        if items[:2] == ("case", "when") and items[-1] == "end":
            then = next((i for i in top if items[i] == "then"), None)
            otherwise = next((i for i in top if items[i] == "else"), None)
            if then is not None and otherwise is not None:
                return ("case", normalize(items[2:then]), normalize(items[then + 1:otherwise]), normalize(items[otherwise + 1:-1]))
        comparison_operators = {"=", "<>", "!=", "<=", ">=", "<", ">", "is"}
        if (not any(items[i] in {"or", "and"} for i in top)
                and sum(items[i] in comparison_operators for i in top) > 1):
            # Do not infer precedence between chained SQL comparisons.
            return ("syntax", *items)
        for operator in ("or", "and", "=", "<>", "!=", "<=", ">=", "<", ">", "is", "as"):
            positions = [i for i in top if items[i] == operator]
            if positions:
                bounds = [-1, *positions, len(items)]
                operands = [normalize(items[a + 1:b]) for a, b in zip(bounds, bounds[1:])]
                if operator in {"and", "or"}:
                    operands = [part for operand in operands for part in (operand[1:] if operand and operand[0] == operator else (operand,))]
                return (operator, *operands)
        if len(items) > 2 and items[1] == "(" and top == [0, len(items) - 1]:
            arguments = items[2:-1]
            depth, bounds = 0, [-1]
            for i, token in enumerate(arguments):
                if token == "(": depth += 1
                elif token == ")": depth -= 1
                elif token == "," and depth == 0: bounds.append(i)
            bounds.append(len(arguments))
            return ("call", items[0], *(normalize(arguments[a + 1:b]) for a, b in zip(bounds, bounds[1:])))
        return ("syntax", *items)

    return normalize(tokens)


def _expected_index(index: IndexSpec) -> tuple[tuple[str, ...], tuple[int | None, ...]]:
    columns, prefixes = [], []
    for value in index.columns:
        match = re.fullmatch(r"([^()]+)\((\d+)\)", value)
        columns.append((match.group(1) if match else value).replace("`", ""))
        prefixes.append(int(match.group(2)) if match else None)
    return tuple(columns), tuple(prefixes)


def _safe_default(column: ColumnSpec) -> bool:
    if column.default is None: return False
    value = _default(column.default) or ""
    if re.search(r"\b(UUID|RAND|NOW)\s*\(", value, re.I): return False
    return not re.search(r"GENERATED", column.extra, re.I)


def diff_schema(expected: ExpectedSchema, actual: SchemaSnapshot) -> SchemaDiff:
    if expected.database_name != actual.database_name:
        raise ValueError("schema_database_mismatch")
    safe, manual = [], []
    expected_tables = {table.name: table for table in expected.tables}
    actual_tables = {table.name: table for table in actual.tables}
    for name, table in sorted(expected_tables.items()):
        if name not in actual_tables:
            safe.append(SchemaDifference("missing_table", name, expected_object=table))
    for name in sorted(actual_tables.keys() - expected_tables.keys()):
        manual.append(SchemaDifference("unexpected_table", name))
    for name in sorted(expected_tables.keys() & actual_tables.keys()):
        expected_table, actual_table = expected_tables[name], actual_tables[name]
        expected_columns = {column.name: column for column in expected_table.columns}
        actual_columns = {column.name: column for column in actual_table.columns}
        for column_name, column in expected_columns.items():
            if column_name not in actual_columns:
                if column.generation_expression is not None:
                    manual.append(SchemaDifference("missing_generated_column", name, column_name))
                elif column.nullable:
                    safe.append(SchemaDifference("missing_nullable_column", name, column_name, expected_object=column))
                elif _safe_default(column):
                    safe.append(SchemaDifference("missing_defaulted_column", name, column_name, expected_object=column))
                else:
                    manual.append(SchemaDifference("missing_required_column_without_backfill", name, column_name))
                continue
            live = actual_columns[column_name]
            if _type(column.data_type) != _type(live.column_type):
                manual.append(SchemaDifference("type_mismatch", name, column_name, _type(column.data_type), _type(live.column_type)))
            if column.nullable != live.nullable:
                manual.append(SchemaDifference("nullability_mismatch", name, column_name, column.nullable, live.nullable))
            expected_default = _default(column.default, column.data_type)
            actual_default = _default(live.default, column.data_type)
            if (column.generation_expression is not None and live.generation_expression
                    and live.default is not None
                    and _expression(live.default) == _expression(live.generation_expression)):
                # OceanBase exposes the generation expression as COLUMN_DEFAULT.
                actual_default = None
            if expected_default != actual_default:
                manual.append(SchemaDifference("default_mismatch", name, column_name, expected_default, actual_default))
            if _extra(column.extra) != _extra(live.extra):
                manual.append(SchemaDifference("extra_mismatch", name, column_name, _extra(column.extra), _extra(live.extra)))
            if _expression(column.generation_expression) != _expression(live.generation_expression):
                manual.append(SchemaDifference("generated_expression_mismatch", name, column_name,
                    column.generation_expression, live.generation_expression))
        for column_name in sorted(actual_columns.keys() - expected_columns.keys()):
            manual.append(SchemaDifference("unexpected_column", name, column_name))
        expected_indexes = {index.name: index for index in expected_table.indexes}
        actual_indexes = {index.name: index for index in actual_table.indexes}
        for index_name, index in sorted(expected_indexes.items()):
            if index_name not in actual_indexes:
                kind = "primary_key_mismatch" if index.primary else "missing_index"
                target = manual if index.primary else safe
                target.append(SchemaDifference(kind, name, index_name, expected_object=index))
                continue
            live = actual_indexes[index_name]
            expected_columns, expected_prefixes = _expected_index(index)
            if (expected_columns != live.columns or expected_prefixes != live.prefix_lengths
                    or index.unique != live.unique or live.index_type != "BTREE"):
                kind = "primary_key_mismatch" if index.primary else "conflicting_index"
                manual.append(SchemaDifference(kind, name, index_name,
                    {"columns": list(expected_columns), "prefix_lengths": list(expected_prefixes), "unique": index.unique, "type": "BTREE"},
                    {"columns": list(live.columns), "prefix_lengths": list(live.prefix_lengths), "unique": live.unique, "type": live.index_type}))
        for index_name in sorted(actual_indexes.keys() - expected_indexes.keys()):
            manual.append(SchemaDifference("unexpected_index", name, index_name))
    order_safe = {"missing_table": 0, "missing_nullable_column": 1, "missing_defaulted_column": 1, "missing_index": 2}
    order_manual = {"type_mismatch": 0, "unexpected_column": 1}
    safe.sort(key=lambda item: (order_safe.get(item.kind, 99), item.table, item.object_name or ""))
    manual.sort(key=lambda item: (order_manual.get(item.kind, 99), item.table, item.object_name or "", item.kind))
    return SchemaDiff(expected.database_name, expected.schema_sha256, tuple(safe), tuple(manual))
