"""Fail-closed per-domain runtime and DDL database configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import unquote, urlparse

from .domain_manifest import DomainManifest


class DomainDatabaseConfigurationError(ValueError):
    """Raised when a domain database URL violates its manifest contract."""


@dataclass(frozen=True)
class DomainDatabaseUrl:
    scheme: str
    host: str
    port: int
    username: str
    password: str
    database: str

    def __repr__(self) -> str:
        return (
            f"DomainDatabaseUrl(scheme={self.scheme!r}, host={self.host!r}, "
            f"port={self.port!r}, username={self.username!r}, password='********', "
            f"database={self.database!r})"
        )


@dataclass(frozen=True)
class DomainDatabaseConfig:
    domain_id: str
    database_name: str
    runtime_url: DomainDatabaseUrl
    ddl_url: DomainDatabaseUrl


def _parse_url(value: str, *, env_name: str, database_name: str) -> DomainDatabaseUrl:
    try:
        parsed = urlparse(value)
        port = parsed.port or 3306
    except ValueError as exc:
        raise DomainDatabaseConfigurationError(f"invalid_database_url: {env_name}") from exc

    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = unquote(parsed.path.removeprefix("/"))
    if (
        parsed.scheme not in {"mysql", "mysql+pymysql"}
        or not parsed.hostname
        or not username
        or not password
        or not database
        or "/" in database
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise DomainDatabaseConfigurationError(f"invalid_database_url: {env_name}")
    if database != database_name:
        raise DomainDatabaseConfigurationError(
            f"database_name_mismatch: {env_name} must target {database_name}"
        )
    return DomainDatabaseUrl(
        scheme=parsed.scheme,
        host=parsed.hostname,
        port=port,
        username=username,
        password=password,
        database=database,
    )


def load_domain_database_config(
    manifest: DomainManifest,
    environ: Mapping[str, str],
) -> DomainDatabaseConfig:
    runtime_env = manifest.database.runtime_url_env
    ddl_env = manifest.database.ddl_url_env
    runtime_value = str(environ.get(runtime_env, "")).strip()
    ddl_value = str(environ.get(ddl_env, "")).strip()
    missing = [name for name, value in ((runtime_env, runtime_value), (ddl_env, ddl_value)) if not value]
    if missing:
        raise DomainDatabaseConfigurationError(
            "missing_domain_database_url: " + ", ".join(missing)
        )

    runtime_url = _parse_url(
        runtime_value,
        env_name=runtime_env,
        database_name=manifest.database.database_name,
    )
    ddl_url = _parse_url(
        ddl_value,
        env_name=ddl_env,
        database_name=manifest.database.database_name,
    )
    if runtime_url.username == ddl_url.username:
        raise DomainDatabaseConfigurationError(
            f"credential_separation_required: {runtime_env} and {ddl_env}"
        )
    return DomainDatabaseConfig(
        domain_id=manifest.domain_id,
        database_name=manifest.database.database_name,
        runtime_url=runtime_url,
        ddl_url=ddl_url,
    )


def _connect(url: DomainDatabaseUrl):
    import pymysql

    return pymysql.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database,
        charset="utf8mb4",
        autocommit=False,
    )


def connect_runtime(config: DomainDatabaseConfig):
    return _connect(config.runtime_url)


def connect_ddl(config: DomainDatabaseConfig):
    return _connect(config.ddl_url)


__all__ = [
    "DomainDatabaseConfig",
    "DomainDatabaseConfigurationError",
    "DomainDatabaseUrl",
    "connect_ddl",
    "connect_runtime",
    "load_domain_database_config",
]
