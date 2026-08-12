"""Live, zero-impact verification of per-domain runtime database grants."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Callable, Mapping

from .domain_database import (
    DomainDatabaseUrl,
    load_domain_database_config,
)
from .domain_manifest import load_domain_manifests
from .domain_migrations import discover_domain_migrations


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ACCESS_DENIED_CODES = frozenset({1044, 1045, 1142, 1143})


class DatabaseIsolationError(RuntimeError):
    """Raised when live grants do not prove the eleven-domain boundary."""


@dataclass(frozen=True)
class ExpectedDomainMigration:
    migration_id: str
    filename: str
    checksum: str
    artifact_version: str


@dataclass(frozen=True)
class DatabaseProbeTarget:
    domain_id: str
    database_name: str
    runtime_url_env: str
    ddl_url_env: str
    table_name: str
    migrations: tuple[ExpectedDomainMigration, ...]


def _quoted(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise DatabaseIsolationError("unsafe_probe_identifier")
    return f"`{value}`"


def load_probe_targets(root: Path) -> tuple[DatabaseProbeTarget, ...]:
    manifests = load_domain_manifests(
        root / "backend/capability_v2/official_domains.json"
    )
    inventory = json.loads(
        (root / "backend/governance/table_inventory.json").read_text(encoding="utf-8")
    )
    tables_by_domain: dict[str, list[str]] = {}
    for row in inventory.get("tables", []):
        tables_by_domain.setdefault(str(row.get("runtime_domain") or ""), []).append(
            str(row.get("table") or "")
        )

    targets = []
    for manifest in sorted(manifests.domains, key=lambda item: item.domain_id):
        owned_tables = sorted(
            table for table in tables_by_domain.get(manifest.domain_id, []) if table
        )
        if not owned_tables:
            raise DatabaseIsolationError(
                f"missing_probe_table:{manifest.domain_id}"
            )
        table_name = owned_tables[0]
        _quoted(table_name)
        targets.append(
            DatabaseProbeTarget(
                domain_id=manifest.domain_id,
                database_name=manifest.database.database_name,
                runtime_url_env=manifest.database.runtime_url_env,
                ddl_url_env=manifest.database.ddl_url_env,
                table_name=table_name,
                migrations=tuple(
                    ExpectedDomainMigration(
                        migration_id=migration.migration_id,
                        filename=migration.path.name,
                        checksum=migration.checksum,
                        artifact_version=migration.artifact_version,
                    )
                    for migration in discover_domain_migrations(root, manifest)
                ),
            )
        )
    if len(targets) != 11:
        raise DatabaseIsolationError("database_probe_requires_exactly_eleven_domains")
    return tuple(targets)


def _default_connect(url: DomainDatabaseUrl, ca_path: str):
    import pymysql

    return pymysql.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database,
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
        ssl={"ca": ca_path, "check_hostname": True},
    )


def _error_code(exc: BaseException) -> int | None:
    if not exc.args:
        return None
    try:
        return int(exc.args[0])
    except (TypeError, ValueError):
        return None


def _is_access_denied(exc: BaseException) -> bool:
    return _error_code(exc) in _ACCESS_DENIED_CODES


def _field_name(row: object) -> str:
    if isinstance(row, Mapping):
        value = row.get("Field") or row.get("field")
    elif isinstance(row, (tuple, list)) and row:
        value = row[0]
    else:
        value = None
    field = str(value or "")
    _quoted(field)
    return field


def _owner_probe(connection: object, target: DatabaseProbeTarget) -> str:
    table = _quoted(target.table_name)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT 1 FROM {table} LIMIT 1")
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        field = _field_name(cursor.fetchone())
        column = _quoted(field)
        cursor.execute(f"UPDATE {table} SET {column}={column} WHERE 1=0")
    connection.rollback()
    return field


def _migration_ledger_probe(connection: object, target: DatabaseProbeTarget) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT migration_id, name, checksum, artifact_version "
            "FROM ai00_schema_migrations ORDER BY migration_id"
        )
        rows = cursor.fetchall()
    actual = []
    for row in rows:
        if isinstance(row, Mapping):
            values = (
                row.get("migration_id"),
                row.get("name"),
                row.get("checksum"),
                row.get("artifact_version"),
            )
        else:
            values = tuple(row[:4])
        actual.append(tuple(str(value or "") for value in values))
    expected = [
        (
            migration.migration_id,
            migration.filename.removeprefix(
                f"{migration.migration_id}_"
            ).removesuffix(".sql"),
            migration.checksum,
            migration.artifact_version,
        )
        for migration in target.migrations
    ]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise DatabaseIsolationError(
            f"migration_ledger_mismatch:{target.domain_id}"
        )


def _runtime_ddl_is_denied(
    connection: object,
    target: DatabaseProbeTarget,
) -> bool:
    probe_table = _quoted(f"ai00_rc_ddl_probe_{target.domain_id}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TABLE {probe_table} (probe_id BIGINT NOT NULL)")
    except Exception as exc:
        if _is_access_denied(exc):
            return True
        raise DatabaseIsolationError(
            f"runtime_ddl_probe_failed:{target.domain_id}:{type(exc).__name__}"
        ) from exc
    return False


def _cleanup_runtime_ddl_probe(
    target: DatabaseProbeTarget,
    ddl_url: DomainDatabaseUrl,
    ca_path: str,
    connect: Callable[[DomainDatabaseUrl, str], object],
) -> None:
    connection = None
    try:
        connection = connect(ddl_url, ca_path)
        probe_table = _quoted(f"ai00_rc_ddl_probe_{target.domain_id}")
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {probe_table}")
    except Exception as exc:
        raise DatabaseIsolationError(
            f"runtime_ddl_cleanup_failed:{target.domain_id}:{type(exc).__name__}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def _query_is_denied(connection: object, sql: str) -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    except Exception as exc:
        if _is_access_denied(exc):
            return True
        raise DatabaseIsolationError(
            f"cross_domain_probe_failed:{type(exc).__name__}"
        ) from exc
    return False


def verify_database_grants(
    targets: tuple[DatabaseProbeTarget, ...],
    environ: Mapping[str, str],
    *,
    ca_path: str,
    connect: Callable[[DomainDatabaseUrl, str], object] = _default_connect,
) -> dict:
    if len(targets) != 11 or not ca_path:
        raise DatabaseIsolationError("database_probe_configuration_invalid")

    manifests = {
        item.domain_id: item
        for item in load_domain_manifests(
            Path(__file__).resolve().parents[2]
            / "backend/capability_v2/official_domains.json"
        ).domains
    }
    configs = {
        target.domain_id: load_domain_database_config(
            manifests[target.domain_id], environ
        )
        for target in targets
    }
    urls = {
        domain_id: config.runtime_url for domain_id, config in configs.items()
    }
    ddl_urls = {
        domain_id: config.ddl_url for domain_id, config in configs.items()
    }
    owner_operations: dict[str, dict[str, str]] = {}
    owner_columns: dict[str, str] = {}
    for target in targets:
        ddl_connection = None
        try:
            ddl_connection = connect(ddl_urls[target.domain_id], ca_path)
            _migration_ledger_probe(ddl_connection, target)
        except Exception as exc:
            if isinstance(exc, DatabaseIsolationError):
                raise
            raise DatabaseIsolationError(
                f"migration_ledger_probe_failed:{target.domain_id}:"
                f"{type(exc).__name__}"
            ) from exc
        finally:
            if ddl_connection is not None:
                ddl_connection.close()
        connection = None
        runtime_ddl_denied = False
        try:
            connection = connect(urls[target.domain_id], ca_path)
            owner_columns[target.domain_id] = _owner_probe(connection, target)
            runtime_ddl_denied = _runtime_ddl_is_denied(connection, target)
        except Exception as exc:
            if isinstance(exc, DatabaseIsolationError):
                raise
            raise DatabaseIsolationError(
                f"owner_probe_failed:{target.domain_id}:{type(exc).__name__}"
            ) from exc
        finally:
            if connection is not None:
                connection.close()
        if not runtime_ddl_denied:
            _cleanup_runtime_ddl_probe(
                target,
                ddl_urls[target.domain_id],
                ca_path,
                connect,
            )
            raise DatabaseIsolationError(
                f"runtime_ddl_allowed:{target.domain_id}"
            )
        owner_operations[target.domain_id] = {
            "migration_ledger": "passed",
            "database_read": "passed",
            "database_write": "passed",
            "runtime_ddl": "denied",
        }

    cross_domain = []
    for source in targets:
        source_url = urls[source.domain_id]
        for target in targets:
            if source.domain_id == target.domain_id:
                continue
            target_url = urls[target.domain_id]
            cross_url = DomainDatabaseUrl(
                scheme=target_url.scheme,
                host=target_url.host,
                port=target_url.port,
                username=source_url.username,
                password=source_url.password,
                database=target_url.database,
            )
            connection = None
            try:
                connection = connect(cross_url, ca_path)
            except Exception as exc:
                if _is_access_denied(exc):
                    cross_domain.append(
                        {
                            "source_domain": source.domain_id,
                            "target_domain": target.domain_id,
                            "read": "denied",
                            "write": "denied",
                        }
                    )
                    continue
                raise DatabaseIsolationError(
                    f"cross_domain_connect_failed:{source.domain_id}:{target.domain_id}:"
                    f"{type(exc).__name__}"
                ) from exc
            try:
                table = _quoted(target.table_name)
                column = _quoted(owner_columns[target.domain_id])
                read_denied = _query_is_denied(
                    connection, f"SELECT 1 FROM {table} LIMIT 1"
                )
                if not read_denied:
                    raise DatabaseIsolationError(
                        f"cross_domain_read_allowed:{source.domain_id}:{target.domain_id}"
                    )
                write_denied = _query_is_denied(
                    connection,
                    f"UPDATE {table} SET {column}={column} WHERE 1=0",
                )
                if not write_denied:
                    raise DatabaseIsolationError(
                        f"cross_domain_write_allowed:{source.domain_id}:{target.domain_id}"
                    )
                cross_domain.append(
                    {
                        "source_domain": source.domain_id,
                        "target_domain": target.domain_id,
                        "read": "denied",
                        "write": "denied",
                    }
                )
            finally:
                connection.close()

    return {
        "owner_operations": owner_operations,
        "cross_domain": cross_domain,
    }


__all__ = [
    "DatabaseIsolationError",
    "DatabaseProbeTarget",
    "ExpectedDomainMigration",
    "load_probe_targets",
    "verify_database_grants",
]
