from __future__ import annotations

from pathlib import Path

import pytest

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.rc_database_bootstrap import (
    BootstrapError,
    BootstrapRequest,
    build_bootstrap_plan,
    execute_bootstrap_plan,
    validate_bootstrap_target,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "backend/capability_v2/official_domains.json"


class RecordingCursor:
    def __init__(self, connection: "RecordingConnection"):
        self.connection = connection
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters=None):
        self.sql = str(sql)
        self.connection.queries.append((self.sql, parameters))
        if self.sql.lstrip().upper().startswith(("CREATE ", "GRANT ", "ALTER ", "DROP ")):
            self.connection.mutations.append((self.sql, parameters))

    def fetchone(self):
        if self.sql == "SELECT VERSION() AS version":
            return {"version": self.connection.version}
        if self.sql == "SHOW VARIABLES LIKE 'ob_compatibility_mode'":
            return {"Variable_name": "ob_compatibility_mode", "Value": self.connection.mode}
        if self.sql == "SELECT @@sql_mode AS sql_mode":
            return {"sql_mode": self.connection.sql_mode}
        return None

    def fetchall(self):
        if "DBA_OB_TENANTS" in self.sql:
            return tuple(self.connection.tenant_rows)
        return ()


class RecordingConnection:
    def __init__(
        self,
        *,
        tenant: str = "capability_test",
        tenant_type: str = "USER",
        version: str = "OceanBase_CE 4.3.5.1",
        mode: str = "MYSQL",
        sql_mode: str = "STRICT_TRANS_TABLES,NO_ZERO_DATE",
        tenant_rows: tuple[dict[str, str], ...] | None = None,
    ):
        self.version = version
        self.mode = mode
        self.sql_mode = sql_mode
        self.tenant_rows = tenant_rows or (
            {
                "TENANT_NAME": tenant,
                "TENANT_TYPE": tenant_type,
                "COMPATIBILITY_MODE": mode,
            },
        )
        self.queries: list[tuple[str, object]] = []
        self.mutations: list[tuple[str, object]] = []

    def cursor(self):
        return RecordingCursor(self)


@pytest.mark.parametrize(
    ("tenant", "environment_id", "host", "allowed", "message"),
    [
        ("sys", "capability-v2-rc", "127.0.0.1", None, "tenant_sys_forbidden"),
        ("customer", "capability-v2-rc", "127.0.0.1", None, "tenant_not_test_or_rc"),
        (
            "capability_test",
            "production-rc",
            "127.0.0.1",
            None,
            "production_environment_forbidden",
        ),
        (
            "capability_test",
            "capability-v2-rc",
            "db.example",
            None,
            "host_not_allowed",
        ),
        (
            "capability_test",
            "capability-v2-rc",
            "db.example",
            "other.example",
            "host_not_allowed",
        ),
    ],
)
def test_validate_bootstrap_target_fails_before_mutation(
    tenant, environment_id, host, allowed, message
):
    connection = RecordingConnection(tenant=tenant)
    request = BootstrapRequest(
        environment_id=environment_id,
        host=host,
        allow_host=allowed,
        url_tenant=tenant,
    )

    with pytest.raises(BootstrapError, match=message):
        validate_bootstrap_target(connection, request)

    assert connection.mutations == []


@pytest.mark.parametrize(
    ("connection", "message"),
    [
        (RecordingConnection(version="OceanBase_CE 4.3.4.9"), "server_contract_invalid"),
        (RecordingConnection(mode="ORACLE"), "server_contract_invalid"),
        (RecordingConnection(sql_mode="NO_ZERO_DATE"), "server_contract_invalid"),
        (
            RecordingConnection(
                tenant_rows=(
                    {
                        "TENANT_NAME": "capability_test",
                        "TENANT_TYPE": "USER",
                        "COMPATIBILITY_MODE": "MYSQL",
                    },
                    {
                        "TENANT_NAME": "other_test",
                        "TENANT_TYPE": "USER",
                        "COMPATIBILITY_MODE": "MYSQL",
                    },
                )
            ),
            "tenant_context_invalid",
        ),
    ],
)
def test_validate_bootstrap_target_rejects_invalid_server_contract_before_mutation(
    connection, message
):
    request = BootstrapRequest(
        environment_id="capability-v2-rc",
        host="127.0.0.1",
        url_tenant="capability_test",
    )

    with pytest.raises(BootstrapError, match=message):
        validate_bootstrap_target(connection, request)

    assert connection.mutations == []


def test_validate_bootstrap_target_rejects_url_tenant_mismatch():
    connection = RecordingConnection(tenant="capability_test")
    request = BootstrapRequest(
        environment_id="capability-v2-rc",
        host="127.0.0.1",
        url_tenant="different_test",
    )

    with pytest.raises(BootstrapError, match="tenant_url_mismatch"):
        validate_bootstrap_target(connection, request)

    assert connection.mutations == []


def test_validate_bootstrap_target_accepts_loopback_user_test_tenant():
    connection = RecordingConnection()
    request = BootstrapRequest(
        environment_id="capability-v2-local-rc",
        host="127.0.0.1",
        url_tenant="capability_test",
    )

    assert validate_bootstrap_target(connection, request) == "capability_test"
    assert connection.mutations == []
    assert any("DBA_OB_TENANTS" in sql for sql, _ in connection.queries)


def test_build_bootstrap_plan_covers_exact_manifest_with_unique_credentials():
    manifests = load_domain_manifests(MANIFEST)
    request = BootstrapRequest(
        environment_id="capability-v2-local-rc",
        host="127.0.0.1",
        url_tenant="capability_test",
    )

    plan = build_bootstrap_plan(
        ROOT,
        request,
        tenant="capability_test",
        port=2881,
    )

    assert plan.schema_version == 1
    assert len(plan.domains) == 11
    assert {domain.domain_id for domain in plan.domains} == {
        item.domain_id for item in manifests.domains
    }
    assert {domain.database_name for domain in plan.domains} == {
        item.database.database_name for item in manifests.domains
    }
    assert {domain.runtime_env for domain in plan.domains} == {
        item.database.runtime_url_env for item in manifests.domains
    }
    assert {domain.ddl_env for domain in plan.domains} == {
        item.database.ddl_url_env for item in manifests.domains
    }
    assert len({domain.runtime_user for domain in plan.domains}) == 11
    assert len({domain.ddl_user for domain in plan.domains}) == 11
    passwords = {
        password
        for domain in plan.domains
        for password in (domain.runtime_password, domain.ddl_password)
    }
    assert len(passwords) == 22
    assert all(len(password) >= 32 for password in passwords)
    assert "password=" not in repr(plan)
    assert all(password not in repr(plan) for password in passwords)


def test_execute_bootstrap_plan_uses_database_local_least_privilege_grants():
    request = BootstrapRequest(
        environment_id="capability-v2-local-rc",
        host="127.0.0.1",
        url_tenant="capability_test",
    )
    plan = build_bootstrap_plan(
        ROOT,
        request,
        tenant="capability_test",
        port=2881,
    )
    connection = RecordingConnection()

    ledger = execute_bootstrap_plan(connection, plan)

    statements = [sql for sql, _ in connection.mutations]
    assert len(ledger) == 33
    assert sum(sql.startswith("CREATE DATABASE") for sql in statements) == 11
    assert sum(sql.startswith("CREATE USER") for sql in statements) == 22
    runtime_grants = [sql for sql in statements if sql.startswith("GRANT SELECT, INSERT")]
    ddl_grants = [sql for sql in statements if sql.startswith("GRANT CREATE, ALTER")]
    assert len(runtime_grants) == 11
    assert len(ddl_grants) == 11
    assert all("SELECT, INSERT, UPDATE, DELETE ON `ai00_" in sql for sql in runtime_grants)
    assert all(
        "CREATE, ALTER, DROP, INDEX, REFERENCES, SELECT, INSERT, UPDATE, DELETE"
        in sql
        for sql in ddl_grants
    )
    assert all("*.*" not in sql for sql in runtime_grants + ddl_grants)
    assert all(" GRANT OPTION" not in sql for sql in runtime_grants + ddl_grants)
    assert all("CREATE USER" not in sql for sql in runtime_grants + ddl_grants)
    assert all(
        domain.runtime_password not in "\n".join(statements)
        and domain.ddl_password not in "\n".join(statements)
        for domain in plan.domains
    )


def test_execute_bootstrap_plan_stops_with_secret_safe_phase_error():
    request = BootstrapRequest(
        environment_id="capability-v2-local-rc",
        host="127.0.0.1",
        url_tenant="capability_test",
    )
    plan = build_bootstrap_plan(
        ROOT,
        request,
        tenant="capability_test",
        port=2881,
    )

    class FailingCursor(RecordingCursor):
        def execute(self, sql, parameters=None):
            super().execute(sql, parameters)
            if str(sql).startswith("CREATE USER"):
                raise RuntimeError("driver included a secret")

    class FailingConnection(RecordingConnection):
        def cursor(self):
            return FailingCursor(self)

    with pytest.raises(BootstrapError, match="bootstrap_execution_failed:user:") as error:
        execute_bootstrap_plan(FailingConnection(), plan)

    rendered = str(error.value)
    assert "driver included" not in rendered
    assert all(domain.runtime_password not in rendered for domain in plan.domains)
    assert all(domain.ddl_password not in rendered for domain in plan.domains)
