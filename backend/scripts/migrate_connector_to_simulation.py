#!/usr/bin/env python3
"""Copy legacy Connector rows into Simulation without mutating the source."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Protocol, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.domain_database import connect_domain_database


@dataclass(frozen=True)
class TableMapping:
    source: str
    target: str
    target_key_fields: tuple[str, ...]
    renames: tuple[tuple[str, str], ...] = ()


TABLE_MAPPINGS = (
    TableMapping("workmanship_runtime_devices", "workmanship_sim_connector_bindings", ("connector_id",), (("gid", "connector_id"),)),
    TableMapping("workmanship_runtime_enrollments", "workmanship_sim_connector_enrollments", ("gid",)),
    TableMapping("workmanship_runtime_commands", "workmanship_sim_connector_legacy_commands", ("gid",), (("device_gid", "connector_id"),)),
    TableMapping("workmanship_device_connector_health", "workmanship_sim_connector_health", ("connector_id",), (("device_gid", "connector_id"),)),
    TableMapping("workmanship_device_connector_heartbeat_audit", "workmanship_sim_connector_heartbeat_audit", ("gid",), (("device_gid", "connector_id"),)),
    TableMapping("workmanship_device_connector_plans", "workmanship_sim_connector_plans", ("plan_id",), (("device_gid", "connector_id"),)),
    TableMapping(
        "workmanship_device_connector_projection_outbox",
        "workmanship_sim_connector_projection_outbox",
        ("plan_id", "outcome_hash", "target_capability"),
    ),
)

_JSON_COLUMNS = frozenset({
    "capabilities", "payload", "result", "health_json", "plan_json", "outcome_json",
})


class RowStore(Protocol):
    def read_rows(self, table: str) -> tuple[dict[str, Any], ...]:
        raise NotImplementedError

    def read_row(self, table: str, key: tuple[object, ...]) -> dict[str, Any] | None:
        raise NotImplementedError

    def insert_row(self, table: str, row: dict[str, Any]) -> None:
        raise NotImplementedError


class MigrationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationReport:
    source_counts: dict[str, int]
    target_counts: dict[str, int]
    source_hashes: dict[str, str]
    target_hashes: dict[str, str]


def _normalise(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalise(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, datetime):
        current = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _canonical_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return _normalise(dict(row))


def _target_row(mapping: TableMapping, row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for source, target in mapping.renames:
        result[target] = result.pop(source)
    return result


def _target_rows(mapping: TableMapping, rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    mapped = tuple(_target_row(mapping, row) for row in rows)
    if mapping.target != "workmanship_sim_connector_projection_outbox":
        return mapped
    latest: dict[tuple[object, ...], dict[str, Any]] = {}
    for row in mapped:
        key = tuple(row[field] for field in mapping.target_key_fields)
        current = latest.get(key)
        if current is None or int(row["attempt"]) > int(current["attempt"]):
            latest[key] = row
    return tuple(latest[key] for key in sorted(latest, key=lambda item: tuple(str(value) for value in item)))


def _row_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    encoded = json.dumps(
        sorted((_canonical_row(row) for row in rows), key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _project(row: Mapping[str, Any], columns: Sequence[str]) -> dict[str, Any]:
    return {column: row.get(column) for column in columns}


def migrate_connector_rows(source: RowStore, target: RowStore) -> MigrationReport:
    source_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    source_hashes: dict[str, str] = {}
    target_hashes: dict[str, str] = {}
    for mapping in TABLE_MAPPINGS:
        source_rows = _target_rows(mapping, source.read_rows(mapping.source))
        for row in source_rows:
            key = tuple(row[field] for field in mapping.target_key_fields)
            current = target.read_row(mapping.target, key)
            if current is None:
                target.insert_row(mapping.target, dict(row))
            elif _canonical_row(_project(current, tuple(row))) != _canonical_row(row):
                printable = ":".join(str(item) for item in key)
                raise MigrationConflict(f"{mapping.target}:{printable}")
        target_rows = target.read_rows(mapping.target)
        columns = tuple(sorted({column for row in source_rows for column in row}))
        comparable_target_rows = tuple(_project(row, columns) for row in target_rows)
        name = mapping.target
        source_counts[name] = len(source_rows)
        target_counts[name] = len(target_rows)
        source_hashes[name] = _row_hash(source_rows)
        target_hashes[name] = _row_hash(comparable_target_rows)
        if source_counts[name] != target_counts[name] or source_hashes[name] != target_hashes[name]:
            raise MigrationConflict(f"{mapping.target}:verification_failed")
    return MigrationReport(source_counts, target_counts, source_hashes, target_hashes)


class MySqlRowStore:
    def __init__(self, connection, mappings: Sequence[TableMapping]) -> None:
        self.connection = connection
        self.keys = {item.target: item.target_key_fields for item in mappings}

    @staticmethod
    def _decode(row: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(row)
        for column in _JSON_COLUMNS & value.keys():
            if isinstance(value[column], str):
                value[column] = json.loads(value[column])
        return value

    def read_rows(self, table: str) -> tuple[dict[str, Any], ...]:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{table}`")
                return tuple(self._decode(row) for row in cursor.fetchall())
        except Exception as exc:
            if getattr(exc, "args", (None,))[0] == 1146:
                return ()
            raise

    def read_row(self, table: str, key: tuple[object, ...]) -> dict[str, Any] | None:
        fields = self.keys[table]
        predicate = " AND ".join(f"`{field}`=%s" for field in fields)
        with self.connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM `{table}` WHERE {predicate} LIMIT 1", key)
            row = cursor.fetchone()
        return self._decode(row) if row else None

    def insert_row(self, table: str, row: dict[str, Any]) -> None:
        columns = tuple(row)
        placeholders = ",".join("%s" for _ in columns)
        names = ",".join(f"`{name}`" for name in columns)
        values = tuple(
            json.dumps(row[name], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if name in _JSON_COLUMNS and isinstance(row[name], (dict, list))
            else row[name]
            for name in columns
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO `{table}` ({names}) VALUES ({placeholders})",
                values,
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-device-db-url", required=True)
    parser.add_argument("--target-simulation-db-url", required=True)
    args = parser.parse_args(argv)
    if args.source_device_db_url == args.target_simulation_db_url:
        parser.error("source and target database URLs must differ")
    source_connection = connect_domain_database(args.source_device_db_url)
    target_connection = connect_domain_database(args.target_simulation_db_url)
    try:
        report = migrate_connector_rows(
            MySqlRowStore(source_connection, TABLE_MAPPINGS),
            MySqlRowStore(target_connection, TABLE_MAPPINGS),
        )
        target_connection.commit()
        print(json.dumps(report.__dict__, sort_keys=True, separators=(",", ":")))
    except Exception:
        target_connection.rollback()
        raise
    finally:
        source_connection.close()
        target_connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
