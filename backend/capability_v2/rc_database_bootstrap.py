"""Fail-closed planning and execution for Capability V2 RC databases."""
from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from pathlib import Path
import re
import secrets
from typing import Callable
from urllib.parse import quote, unquote, urlparse

from backend.db.oceanbase_compat import verify_live_server

from .domain_manifest import load_domain_manifests


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_DDL_PRIVILEGES = (
    "CREATE, ALTER, DROP, INDEX, REFERENCES, SELECT, INSERT, UPDATE, DELETE"
)
_RUNTIME_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"


class BootstrapError(RuntimeError):
    """Raised when bootstrap safety or least-privilege requirements fail."""


@dataclass(frozen=True)
class BootstrapRequest:
    environment_id: str
    host: str
    allow_host: str | None = None
    url_tenant: str = ""


@dataclass(frozen=True)
class BootstrapDomain:
    domain_id: str
    database_name: str
    runtime_env: str
    ddl_env: str
    runtime_user: str
    ddl_user: str
    runtime_password: str = field(repr=False)
    ddl_password: str = field(repr=False)


@dataclass(frozen=True)
class BootstrapPlan:
    schema_version: int
    environment_id: str
    tenant: str
    host: str
    port: int
    domains: tuple[BootstrapDomain, ...]


@dataclass(frozen=True)
class ReuseCredential:
    domain_id: str
    role: str
    env_name: str
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    database: str = ""


@dataclass(frozen=True)
class ReuseEnvironment:
    schema_version: int
    environment_id: str
    tenant: str
    host: str
    port: int
    credentials: tuple[ReuseCredential, ...]
    document: str = field(repr=False)


def _row_value(row: object, name: str, index: int) -> str:
    if isinstance(row, dict):
        value = row.get(name)
        if value is None:
            value = row.get(name.lower())
    elif isinstance(row, (tuple, list)) and len(row) > index:
        value = row[index]
    else:
        value = None
    return str(value or "").strip()


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_environment_id(value: str) -> None:
    normalized = value.strip().casefold()
    if "prod" in normalized or "production" in normalized:
        raise BootstrapError("production_environment_forbidden")
    if not normalized or not any(marker in normalized for marker in ("test", "rc")):
        raise BootstrapError("environment_not_test_or_rc")


def validate_bootstrap_target(connection: object, request: BootstrapRequest) -> str:
    """Validate every target guard before any database object is created."""

    _validate_environment_id(request.environment_id)
    host = request.host.strip().casefold()
    allowed = (request.allow_host or "").strip().casefold()
    if not _is_loopback(host) and host != allowed:
        raise BootstrapError("host_not_allowed")

    try:
        verify_live_server(connection)
    except Exception as exc:
        raise BootstrapError("server_contract_invalid") from None

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT TENANT_NAME, TENANT_TYPE, COMPATIBILITY_MODE "
                "FROM oceanbase.DBA_OB_TENANTS"
            )
            rows = tuple(cursor.fetchall())
    except Exception:
        raise BootstrapError("tenant_context_unreadable") from None
    if len(rows) != 1:
        raise BootstrapError("tenant_context_invalid")

    tenant = _row_value(rows[0], "TENANT_NAME", 0)
    tenant_type = _row_value(rows[0], "TENANT_TYPE", 1).upper()
    compatibility_mode = _row_value(rows[0], "COMPATIBILITY_MODE", 2).upper()
    normalized_tenant = tenant.casefold()
    if normalized_tenant == "sys" or tenant_type == "SYS":
        raise BootstrapError("tenant_sys_forbidden")
    if tenant_type != "USER" or compatibility_mode != "MYSQL":
        raise BootstrapError("tenant_context_invalid")
    if "prod" in normalized_tenant or "production" in normalized_tenant:
        raise BootstrapError("production_tenant_forbidden")
    if not any(marker in normalized_tenant for marker in ("test", "rc")):
        raise BootstrapError("tenant_not_test_or_rc")
    if not request.url_tenant or normalized_tenant != request.url_tenant.casefold():
        raise BootstrapError("tenant_url_mismatch")
    return tenant


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise BootstrapError("unsafe_bootstrap_identifier")
    return f"`{value}`"


def build_bootstrap_plan(
    root: Path,
    request: BootstrapRequest,
    *,
    tenant: str,
    port: int,
    password_factory: Callable[[], str] | None = None,
) -> BootstrapPlan:
    """Build the exact eleven-domain credential plan from the frozen manifest."""

    manifests = load_domain_manifests(
        root / "backend/capability_v2/official_domains.json"
    )
    if len(manifests.domains) != 11:
        raise BootstrapError("bootstrap_requires_exactly_eleven_domains")
    make_password = password_factory or (lambda: secrets.token_urlsafe(32))
    domains: list[BootstrapDomain] = []
    passwords: set[str] = set()
    for manifest in sorted(manifests.domains, key=lambda item: item.domain_id):
        domain_id = manifest.domain_id
        database_name = manifest.database.database_name
        runtime_user = f"ai00_{domain_id}_runtime"
        ddl_user = f"ai00_{domain_id}_ddl"
        for identifier in (domain_id, database_name, runtime_user, ddl_user):
            _identifier(identifier)
        generated: list[str] = []
        for _role in range(2):
            password = make_password()
            if len(password) < 32 or password in passwords:
                raise BootstrapError("generated_password_invalid")
            passwords.add(password)
            generated.append(password)
        domains.append(
            BootstrapDomain(
                domain_id=domain_id,
                database_name=database_name,
                runtime_env=manifest.database.runtime_url_env,
                ddl_env=manifest.database.ddl_url_env,
                runtime_user=runtime_user,
                ddl_user=ddl_user,
                runtime_password=generated[0],
                ddl_password=generated[1],
            )
        )
    return BootstrapPlan(
        schema_version=1,
        environment_id=request.environment_id,
        tenant=tenant,
        host=request.host,
        port=port,
        domains=tuple(domains),
    )


def _execute(
    connection: object,
    sql: str,
    parameters: tuple[object, ...] | None,
    *,
    phase: str,
    domain_id: str,
) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, parameters)
    except Exception:
        raise BootstrapError(
            f"bootstrap_execution_failed:{phase}:{domain_id}"
        ) from None


def _preflight_absent(connection: object, plan: BootstrapPlan) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA "
                "WHERE SCHEMA_NAME LIKE %s",
                ("ai00_%",),
            )
            databases = tuple(cursor.fetchall())
            cursor.execute(
                "SELECT User FROM mysql.user WHERE User LIKE %s",
                ("ai00_%",),
            )
            users = tuple(cursor.fetchall())
    except Exception:
        raise BootstrapError("bootstrap_preflight_failed") from None
    expected_databases = {domain.database_name for domain in plan.domains}
    expected_users = {
        user
        for domain in plan.domains
        for user in (domain.runtime_user, domain.ddl_user)
    }
    existing_databases = {
        _row_value(row, "SCHEMA_NAME", 0) for row in databases
    } & expected_databases
    existing_users = {_row_value(row, "User", 0) for row in users} & expected_users
    if existing_databases or existing_users:
        raise BootstrapError("bootstrap_objects_already_exist")


def execute_bootstrap_plan(
    connection: object,
    plan: BootstrapPlan,
) -> tuple[str, ...]:
    """Execute a preflighted plan and return a non-secret created-object ledger."""

    _preflight_absent(connection, plan)
    ledger: list[str] = []
    for domain in plan.domains:
        database = _identifier(domain.database_name)
        _execute(
            connection,
            f"CREATE DATABASE {database} CHARACTER SET utf8mb4",
            None,
            phase="database",
            domain_id=domain.domain_id,
        )
        ledger.append(f"database:{domain.database_name}")
    for domain in plan.domains:
        for role, user, password in (
            ("ddl", domain.ddl_user, domain.ddl_password),
            ("runtime", domain.runtime_user, domain.runtime_password),
        ):
            _execute(
                connection,
                f"CREATE USER {_identifier(user)} IDENTIFIED BY %s",
                (password,),
                phase="user",
                domain_id=domain.domain_id,
            )
            ledger.append(f"user:{domain.domain_id}:{role}")
    for domain in plan.domains:
        database = _identifier(domain.database_name)
        _execute(
            connection,
            f"GRANT {_DDL_PRIVILEGES} ON {database}.* TO {_identifier(domain.ddl_user)}",
            None,
            phase="ddl_grant",
            domain_id=domain.domain_id,
        )
        _execute(
            connection,
            f"GRANT {_RUNTIME_PRIVILEGES} ON {database}.* TO {_identifier(domain.runtime_user)}",
            None,
            phase="runtime_grant",
            domain_id=domain.domain_id,
        )
    return tuple(ledger)


def _env_value(value: object) -> str:
    rendered = str(value)
    if any(character in rendered for character in ("\r", "\n", "\x00")):
        raise BootstrapError("env_value_invalid")
    return rendered


def _database_url(
    plan: BootstrapPlan,
    domain: BootstrapDomain,
    *,
    role: str,
) -> str:
    if role == "runtime":
        user, password = domain.runtime_user, domain.runtime_password
    elif role == "ddl":
        user, password = domain.ddl_user, domain.ddl_password
    else:
        raise BootstrapError("database_role_invalid")
    username = quote(f"{_env_value(user)}@{_env_value(plan.tenant)}", safe="")
    encoded_password = quote(_env_value(password), safe="")
    return (
        f"mysql+pymysql://{username}:{encoded_password}@{_env_value(plan.host)}:"
        f"{plan.port}/{_env_value(domain.database_name)}"
    )


def render_bootstrap_env(plan: BootstrapPlan) -> str:
    """Render a protected env document without logging any credential."""

    records: list[tuple[str, str]] = [
        ("AI00_RC_BOOTSTRAP_SCHEMA_VERSION", str(plan.schema_version)),
        ("AI00_RC_ENVIRONMENT_ID", plan.environment_id),
        ("AI00_RC_TENANT", plan.tenant),
        ("AI00_RC_HOST", plan.host),
        ("AI00_RC_PORT", str(plan.port)),
    ]
    for domain in plan.domains:
        records.extend(
            (
                (domain.runtime_env, _database_url(plan, domain, role="runtime")),
                (domain.ddl_env, _database_url(plan, domain, role="ddl")),
            )
        )
    seen: set[str] = set()
    lines: list[str] = []
    for name, value in records:
        if name in seen or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise BootstrapError("env_key_invalid")
        seen.add(name)
        lines.append(f"{name}={_env_value(value)}")
    return "\n".join(lines) + "\n"


def _read_env_document(path: Path) -> tuple[dict[str, str], str]:
    try:
        document = path.read_text(encoding="utf-8")
    except Exception:
        raise BootstrapError("reuse_env_unreadable") from None
    if "\x00" in document:
        raise BootstrapError("reuse_env_value_invalid")
    values: dict[str, str] = {}
    for line in document.splitlines():
        if not line or "=" not in line:
            raise BootstrapError("reuse_env_record_invalid")
        name, value = line.split("=", 1)
        if name in values:
            raise BootstrapError("reuse_env_duplicate_key")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise BootstrapError("reuse_env_key_invalid")
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise BootstrapError("reuse_env_value_invalid")
        values[name] = value
    return values, document


def _reuse_credential(
    value: str,
    *,
    domain_id: str,
    role: str,
    env_name: str,
    database_name: str,
    tenant: str,
    host: str,
    port: int,
) -> ReuseCredential:
    try:
        parsed = urlparse(value)
        parsed_port = parsed.port or 3306
    except ValueError:
        raise BootstrapError(f"reuse_url_invalid:{domain_id}:{role}") from None
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = unquote(parsed.path.removeprefix("/"))
    expected_local_user = f"ai00_{domain_id}_{role}"
    if (
        parsed.scheme not in {"mysql", "mysql+pymysql"}
        or parsed.hostname != host
        or parsed_port != port
        or username != f"{expected_local_user}@{tenant}"
        or not password
        or database != database_name
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise BootstrapError(f"reuse_url_mismatch:{domain_id}:{role}")
    return ReuseCredential(
        domain_id=domain_id,
        role=role,
        env_name=env_name,
        host=host,
        port=port,
        username=username,
        password=password,
        database=database,
    )


def parse_reuse_env(
    path: Path,
    root: Path,
    request: BootstrapRequest,
) -> ReuseEnvironment:
    """Parse a tool-owned env file and bind it to the current request/manifest."""

    values, document = _read_env_document(path)
    manifests = load_domain_manifests(
        root / "backend/capability_v2/official_domains.json"
    )
    metadata = {
        "AI00_RC_BOOTSTRAP_SCHEMA_VERSION",
        "AI00_RC_ENVIRONMENT_ID",
        "AI00_RC_TENANT",
        "AI00_RC_HOST",
        "AI00_RC_PORT",
    }
    url_names = {
        name
        for manifest in manifests.domains
        for name in (
            manifest.database.runtime_url_env,
            manifest.database.ddl_url_env,
        )
    }
    if set(values) != metadata | url_names:
        raise BootstrapError("reuse_env_keys_mismatch")
    if values["AI00_RC_BOOTSTRAP_SCHEMA_VERSION"] != "1":
        raise BootstrapError("reuse_schema_mismatch")
    if values["AI00_RC_ENVIRONMENT_ID"] != request.environment_id:
        raise BootstrapError("reuse_environment_mismatch")
    tenant = values["AI00_RC_TENANT"]
    if tenant.casefold() != request.url_tenant.casefold():
        raise BootstrapError("reuse_tenant_mismatch")
    host = values["AI00_RC_HOST"]
    if host.casefold() != request.host.casefold():
        raise BootstrapError("reuse_host_mismatch")
    try:
        port = int(values["AI00_RC_PORT"])
    except ValueError:
        raise BootstrapError("reuse_port_invalid") from None
    if not 1 <= port <= 65535:
        raise BootstrapError("reuse_port_invalid")

    credentials: list[ReuseCredential] = []
    for manifest in sorted(manifests.domains, key=lambda item: item.domain_id):
        for role, env_name in (
            ("runtime", manifest.database.runtime_url_env),
            ("ddl", manifest.database.ddl_url_env),
        ):
            credentials.append(
                _reuse_credential(
                    values[env_name],
                    domain_id=manifest.domain_id,
                    role=role,
                    env_name=env_name,
                    database_name=manifest.database.database_name,
                    tenant=tenant,
                    host=host,
                    port=port,
                )
            )
    return ReuseEnvironment(
        schema_version=1,
        environment_id=request.environment_id,
        tenant=tenant,
        host=host,
        port=port,
        credentials=tuple(credentials),
        document=document,
    )


def _grant_text(row: object) -> str:
    if isinstance(row, dict):
        values = tuple(row.values())
        value = values[0] if values else ""
    elif isinstance(row, (tuple, list)) and row:
        value = row[0]
    else:
        value = ""
    return str(value).strip()


def _grants_are_exact(credential: ReuseCredential, rows: tuple[object, ...]) -> bool:
    expected = (
        set(_RUNTIME_PRIVILEGES.split(", "))
        if credential.role == "runtime"
        else set(_DDL_PRIVILEGES.split(", "))
    )
    found_database_grant = False
    for row in rows:
        grant = _grant_text(row)
        match = re.match(r"^GRANT (.+?) ON (.+?) TO ", grant, re.IGNORECASE)
        if not match:
            return False
        privileges = {item.strip().upper() for item in match.group(1).split(",")}
        target = match.group(2).replace("`", "")
        if privileges == {"USAGE"} and target == "*.*":
            continue
        if target != f"{credential.database}.*" or privileges != expected:
            return False
        if found_database_grant:
            return False
        found_database_grant = True
    return found_database_grant


def verify_reuse_environment(
    environment: ReuseEnvironment,
    *,
    connect: Callable[..., object],
) -> None:
    """Reconnect all 22 principals and prove their grants are still exact."""

    for credential in environment.credentials:
        connection = None
        try:
            connection = connect(
                host=credential.host,
                port=credential.port,
                user=credential.username,
                password=credential.password,
                database=credential.database,
                charset="utf8mb4",
                autocommit=True,
            )
            with connection.cursor() as cursor:
                cursor.execute("SHOW GRANTS")
                rows = tuple(cursor.fetchall())
            if not _grants_are_exact(credential, rows):
                raise BootstrapError(
                    f"reuse_grants_mismatch:{credential.domain_id}:{credential.role}"
                )
        except BootstrapError:
            raise
        except Exception:
            raise BootstrapError(
                f"reuse_verification_failed:{credential.domain_id}:{credential.role}"
            ) from None
        finally:
            if connection is not None:
                close = getattr(connection, "close", None)
                if callable(close):
                    close()


__all__ = [
    "BootstrapDomain",
    "BootstrapError",
    "BootstrapPlan",
    "BootstrapRequest",
    "ReuseCredential",
    "ReuseEnvironment",
    "build_bootstrap_plan",
    "execute_bootstrap_plan",
    "parse_reuse_env",
    "render_bootstrap_env",
    "validate_bootstrap_target",
    "verify_reuse_environment",
]
