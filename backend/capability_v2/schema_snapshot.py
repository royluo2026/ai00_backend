from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


class SnapshotError(RuntimeError):
    pass


TABLE_HEADERS = ("TABLE_SCHEMA", "TABLE_NAME", "ENGINE", "TABLE_COLLATION", "TABLE_TYPE")
COLUMN_HEADERS = (
    "TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "ORDINAL_POSITION", "COLUMN_DEFAULT",
    "IS_NULLABLE", "DATA_TYPE", "COLUMN_TYPE", "COLUMN_KEY", "EXTRA",
    "CHARACTER_SET_NAME", "COLLATION_NAME", "GENERATION_EXPRESSION",
)
INDEX_HEADERS = (
    "TABLE_SCHEMA", "TABLE_NAME", "INDEX_NAME", "NON_UNIQUE", "SEQ_IN_INDEX",
    "COLUMN_NAME", "SUB_PART", "INDEX_TYPE", "COLLATION",
)


@dataclass(frozen=True)
class SnapshotColumn:
    name: str
    ordinal: int
    default: str | None
    nullable: bool
    data_type: str
    column_type: str
    key: str
    extra: str
    charset: str | None
    collation: str | None
    generation_expression: str


@dataclass(frozen=True)
class SnapshotIndex:
    name: str
    columns: tuple[str, ...]
    prefix_lengths: tuple[int | None, ...]
    unique: bool
    index_type: str


@dataclass(frozen=True)
class SnapshotTable:
    name: str
    engine: str
    collation: str
    table_type: str
    columns: tuple[SnapshotColumn, ...]
    indexes: tuple[SnapshotIndex, ...]

    def require_column(self, name: str) -> SnapshotColumn:
        return next(column for column in self.columns if column.name == name)

    def require_index(self, name: str) -> SnapshotIndex:
        return next(index for index in self.indexes if index.name == name)


@dataclass(frozen=True)
class SchemaSnapshot:
    database_name: str
    tables: tuple[SnapshotTable, ...]

    def require_table(self, name: str) -> SnapshotTable:
        return next(table for table in self.tables if table.name == name)


def _rows(path: Path, headers: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        raise SnapshotError(f"missing_snapshot_file:{path.name}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != headers:
            raise SnapshotError(f"invalid_headers:{path.name}")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise SnapshotError(f"malformed_csv_row:{path.name}")
    return rows


def _database(row: dict[str, str], expected: str, file_name: str):
    if row["TABLE_SCHEMA"] != expected:
        raise SnapshotError(f"database_mismatch:{file_name}:{row['TABLE_SCHEMA']}")


def load_schema_snapshot(directory: Path, expected_database: str = "ai00_test") -> SchemaSnapshot:
    directory = Path(directory)
    table_rows = _rows(directory / f"{expected_database}_tables.csv", TABLE_HEADERS)
    column_rows = _rows(directory / f"{expected_database}_columns.csv", COLUMN_HEADERS)
    index_rows = _rows(directory / f"{expected_database}_indexes.csv", INDEX_HEADERS)
    table_data: dict[str, dict[str, object]] = {}
    for row in table_rows:
        _database(row, expected_database, "tables")
        name = row["TABLE_NAME"]
        if name in table_data: raise SnapshotError(f"duplicate_table_row:{name}")
        table_data[name] = {"row": row, "columns": [], "indexes": {}}
    seen_columns = set()
    for row in column_rows:
        _database(row, expected_database, "columns")
        name, column = row["TABLE_NAME"], row["COLUMN_NAME"]
        if name not in table_data: raise SnapshotError(f"column_for_unknown_table:{name}.{column}")
        try: ordinal = int(row["ORDINAL_POSITION"])
        except ValueError as exc: raise SnapshotError(f"invalid_column_ordinal:{name}.{column}") from exc
        key = (name, ordinal)
        if key in seen_columns: raise SnapshotError(f"duplicate_column_row:{name}:{ordinal}")
        seen_columns.add(key)
        if row["IS_NULLABLE"] not in {"YES", "NO"}: raise SnapshotError(f"invalid_nullability:{name}.{column}")
        default = None if row["COLUMN_DEFAULT"] == "<SQL_NULL>" else row["COLUMN_DEFAULT"]
        table_data[name]["columns"].append(SnapshotColumn(
            column, ordinal, default, row["IS_NULLABLE"] == "YES", row["DATA_TYPE"].upper(),
            row["COLUMN_TYPE"].upper(), row["COLUMN_KEY"].upper(), row["EXTRA"].upper(),
            row["CHARACTER_SET_NAME"] or None, row["COLLATION_NAME"] or None,
            row["GENERATION_EXPRESSION"],
        ))
    seen_indexes = set()
    for row in index_rows:
        _database(row, expected_database, "indexes")
        name, index_name = row["TABLE_NAME"], row["INDEX_NAME"]
        if name not in table_data: raise SnapshotError(f"index_for_unknown_table:{name}.{index_name}")
        try: sequence = int(row["SEQ_IN_INDEX"])
        except ValueError as exc: raise SnapshotError(f"invalid_index_sequence:{name}.{index_name}") from exc
        key = (name, index_name, sequence)
        if key in seen_indexes: raise SnapshotError(f"duplicate_index_row:{name}.{index_name}:{sequence}")
        seen_indexes.add(key)
        if row["NON_UNIQUE"] not in {"0", "1"}: raise SnapshotError(f"invalid_non_unique:{name}.{index_name}")
        part = None if row["SUB_PART"] in {"", "NULL", "<SQL_NULL>"} else int(row["SUB_PART"])
        bucket = table_data[name]["indexes"].setdefault(index_name, [])
        bucket.append((sequence, row["COLUMN_NAME"], part, row["NON_UNIQUE"], row["INDEX_TYPE"].upper()))
    tables = []
    for name, data in sorted(table_data.items()):
        row = data["row"]
        indexes = []
        for index_name, entries in sorted(data["indexes"].items()):
            entries.sort()
            if [entry[0] for entry in entries] != list(range(1, len(entries) + 1)):
                raise SnapshotError(f"non_contiguous_index:{name}.{index_name}")
            if len({entry[3] for entry in entries}) != 1 or len({entry[4] for entry in entries}) != 1:
                raise SnapshotError(f"inconsistent_index_metadata:{name}.{index_name}")
            indexes.append(SnapshotIndex(index_name, tuple(entry[1] for entry in entries),
                tuple(entry[2] for entry in entries), entries[0][3] == "0", entries[0][4]))
        tables.append(SnapshotTable(name, row["ENGINE"], row["TABLE_COLLATION"], row["TABLE_TYPE"],
            tuple(sorted(data["columns"], key=lambda column: column.ordinal)), tuple(indexes)))
    return SchemaSnapshot(expected_database, tuple(tables))
