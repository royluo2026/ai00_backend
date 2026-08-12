from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.rc_database_bootstrap import (
    BootstrapError,
    BootstrapRequest,
    build_bootstrap_plan,
    execute_bootstrap_plan,
    parse_reuse_env,
    render_bootstrap_env,
    validate_bootstrap_target,
    verify_reuse_environment,
)
from backend.scripts.bootstrap_capability_v2_rc_databases import main
from backend.scripts import bootstrap_capability_v2_rc_databases as bootstrap_cli


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


def _plan():
    request = BootstrapRequest(
        environment_id="capability-v2-local-rc",
        host="127.0.0.1",
        url_tenant="capability_test",
    )
    return build_bootstrap_plan(
        ROOT,
        request,
        tenant="capability_test",
        port=2881,
    )


def _env_document(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines())


def test_render_bootstrap_env_contains_exact_metadata_and_manifest_urls():
    plan = _plan()
    document = _env_document(render_bootstrap_env(plan))
    manifests = load_domain_manifests(MANIFEST)
    url_names = {
        name
        for manifest in manifests.domains
        for name in (
            manifest.database.runtime_url_env,
            manifest.database.ddl_url_env,
        )
    }

    assert set(document) == {
        "AI00_RC_BOOTSTRAP_SCHEMA_VERSION",
        "AI00_RC_ENVIRONMENT_ID",
        "AI00_RC_TENANT",
        "AI00_RC_HOST",
        "AI00_RC_PORT",
        *url_names,
    }
    assert document["AI00_RC_BOOTSTRAP_SCHEMA_VERSION"] == "1"
    assert document["AI00_RC_ENVIRONMENT_ID"] == plan.environment_id
    assert document["AI00_RC_TENANT"] == plan.tenant
    for domain in plan.domains:
        for name, expected_user, expected_password in (
            (domain.runtime_env, domain.runtime_user, domain.runtime_password),
            (domain.ddl_env, domain.ddl_user, domain.ddl_password),
        ):
            parsed = urlparse(document[name])
            assert parsed.scheme == "mysql+pymysql"
            assert unquote(parsed.username or "") == f"{expected_user}@{plan.tenant}"
            assert unquote(parsed.password or "") == expected_password
            assert parsed.hostname == plan.host
            assert parsed.port == plan.port
            assert parsed.path == f"/{domain.database_name}"


@pytest.mark.parametrize("bad", ["line\nbreak", "carriage\rreturn", "nul\x00byte"])
def test_render_bootstrap_env_rejects_record_injection(bad):
    plan = _plan()
    unsafe = type(plan)(
        schema_version=plan.schema_version,
        environment_id=bad,
        tenant=plan.tenant,
        host=plan.host,
        port=plan.port,
        domains=plan.domains,
    )

    with pytest.raises(BootstrapError, match="env_value_invalid"):
        render_bootstrap_env(unsafe)


def test_bootstrap_cli_reads_named_admin_env_and_atomically_protects_output(
    tmp_path, capsys
):
    output = tmp_path / "capability-v2-rc.env"
    protected: list[Path] = []
    connection = RecordingConnection()
    calls = []

    def fake_connect(**kwargs):
        calls.append(kwargs)
        return connection

    result = main(
        [
            "--admin-url-env",
            "AI00_RC_ADMIN_DB_URL",
            "--environment-id",
            "capability-v2-local-rc",
            "--output-env",
            str(output),
        ],
        environ={
            "AI00_RC_ADMIN_DB_URL": (
                "mysql://root%40capability_test:admin-secret@127.0.0.1:2881/oceanbase"
            )
        },
        connect=fake_connect,
        protect_file=protected.append,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "admin-secret" not in captured.out
    assert "admin-secret" not in captured.err
    assert '"databases": 11' in captured.out
    assert '"principals": 22' in captured.out
    assert protected == [output]
    assert output.is_file()
    assert not output.with_suffix(output.suffix + ".tmp").exists()
    assert calls == [
        {
            "host": "127.0.0.1",
            "port": 2881,
            "user": "root@capability_test",
            "password": "admin-secret",
            "database": "oceanbase",
            "charset": "utf8mb4",
            "autocommit": True,
        }
    ]
    assert connection.mutations
    assert all("admin-secret" not in line for line in output.read_text().splitlines())


@pytest.mark.parametrize(
    ("argv", "environ", "message"),
    [
        (
            [
                "--admin-url-env",
                "AI00_RC_ADMIN_DB_URL",
                "--environment-id",
                "capability-v2-local-rc",
                "--output-env",
                "out.env",
            ],
            {},
            "admin_url_env_missing",
        ),
        (
            [
                "--admin-url-env",
                "AI00_RC_ADMIN_DB_URL",
                "--environment-id",
                "capability-v2-local-rc",
                "--output-env",
                "out.env",
            ],
            {"AI00_RC_ADMIN_DB_URL": "mysql://root:secret@127.0.0.1:2881/not-oceanbase"},
            "admin_url_database_invalid",
        ),
    ],
)
def test_bootstrap_cli_fails_without_safe_named_admin_url(argv, environ, message):
    with pytest.raises(BootstrapError, match=message):
        main(
            argv,
            environ=environ,
            connect=lambda **_kwargs: pytest.fail("must reject before connect"),
            protect_file=lambda _path: pytest.fail("must reject before output"),
        )


class GrantCursor:
    def __init__(self, connection: "GrantConnection"):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters=None):
        self.connection.queries.append((str(sql), parameters))

    def fetchall(self):
        user = self.connection.user.split("@", 1)[0]
        quoted_user = f"`{user}`@`%`"
        if user.endswith("_runtime"):
            privileges = "SELECT, INSERT, UPDATE, DELETE"
        else:
            privileges = (
                "CREATE, ALTER, DROP, INDEX, REFERENCES, SELECT, INSERT, UPDATE, DELETE"
            )
        rows = [
            (f"GRANT USAGE ON *.* TO {quoted_user}",),
            (
                f"GRANT {privileges} ON `{self.connection.database}`.* "
                f"TO {quoted_user}",
            ),
        ]
        if self.connection.extra_grant:
            rows.append((self.connection.extra_grant,))
        return tuple(rows)


class GrantConnection:
    def __init__(self, *, user: str, database: str, extra_grant: str = ""):
        self.user = user
        self.database = database
        self.extra_grant = extra_grant
        self.queries = []
        self.closed = False

    def cursor(self):
        return GrantCursor(self)

    def close(self):
        self.closed = True


def test_parse_and_verify_reuse_env_reconnects_all_exact_minimum_grants(tmp_path):
    plan = _plan()
    env_path = tmp_path / "existing.env"
    env_path.write_text(render_bootstrap_env(plan), encoding="utf-8")
    request = BootstrapRequest(
        environment_id=plan.environment_id,
        host=plan.host,
        url_tenant=plan.tenant,
    )
    reuse = parse_reuse_env(env_path, ROOT, request)
    connections = []

    def connect(**kwargs):
        connection = GrantConnection(user=kwargs["user"], database=kwargs["database"])
        connections.append(connection)
        return connection

    verify_reuse_environment(reuse, connect=connect)

    assert len(connections) == 22
    assert all(connection.queries == [("SHOW GRANTS", None)] for connection in connections)
    assert all(connection.closed for connection in connections)


@pytest.mark.parametrize(
    ("replace_from", "replace_to", "message"),
    [
        (
            "AI00_RC_ENVIRONMENT_ID=capability-v2-local-rc",
            "AI00_RC_ENVIRONMENT_ID=other-test",
            "reuse_environment_mismatch",
        ),
        (
            "AI00_RC_TENANT=capability_test",
            "AI00_RC_TENANT=other_test",
            "reuse_tenant_mismatch",
        ),
        (
            "AI00_AGENT_DB_URL=",
            "AI00_UNKNOWN_DB_URL=",
            "reuse_env_keys_mismatch",
        ),
    ],
)
def test_parse_reuse_env_rejects_metadata_or_domain_key_mismatch(
    tmp_path, replace_from, replace_to, message
):
    plan = _plan()
    text = render_bootstrap_env(plan).replace(replace_from, replace_to, 1)
    path = tmp_path / "bad.env"
    path.write_text(text, encoding="utf-8")
    request = BootstrapRequest(
        environment_id=plan.environment_id,
        host=plan.host,
        url_tenant=plan.tenant,
    )

    with pytest.raises(BootstrapError, match=message):
        parse_reuse_env(path, ROOT, request)


def test_parse_reuse_env_rejects_duplicate_and_record_injection(tmp_path):
    plan = _plan()
    text = render_bootstrap_env(plan)
    first_url = next(line for line in text.splitlines() if line.startswith("AI00_AGENT_DB_URL="))
    duplicate = tmp_path / "duplicate.env"
    duplicate.write_text(text + first_url + "\n", encoding="utf-8")
    request = BootstrapRequest(
        environment_id=plan.environment_id,
        host=plan.host,
        url_tenant=plan.tenant,
    )

    with pytest.raises(BootstrapError, match="reuse_env_duplicate_key"):
        parse_reuse_env(duplicate, ROOT, request)

    injected = tmp_path / "injected.env"
    injected.write_bytes(text.encode("utf-8") + b"AI00_AGENT_DB_URL=bad\x00value\n")
    with pytest.raises(BootstrapError, match="reuse_env_value_invalid"):
        parse_reuse_env(injected, ROOT, request)


def test_verify_reuse_env_rejects_extra_global_grant_without_leaking_password(tmp_path):
    plan = _plan()
    env_path = tmp_path / "existing.env"
    env_path.write_text(render_bootstrap_env(plan), encoding="utf-8")
    request = BootstrapRequest(
        environment_id=plan.environment_id,
        host=plan.host,
        url_tenant=plan.tenant,
    )
    reuse = parse_reuse_env(env_path, ROOT, request)

    def connect(**kwargs):
        extra = "GRANT CREATE USER ON *.* TO `bad`@`%`" if kwargs["user"].startswith("ai00_agent_runtime") else ""
        return GrantConnection(
            user=kwargs["user"], database=kwargs["database"], extra_grant=extra
        )

    with pytest.raises(BootstrapError, match="reuse_grants_mismatch:agent:runtime") as error:
        verify_reuse_environment(reuse, connect=connect)

    rendered = str(error.value)
    assert all(domain.runtime_password not in rendered for domain in plan.domains)
    assert all(domain.ddl_password not in rendered for domain in plan.domains)


def test_bootstrap_cli_reuse_verifies_without_mutation_or_password_rotation(
    tmp_path, capsys
):
    plan = _plan()
    reuse_path = tmp_path / "existing.env"
    reuse_path.write_text(render_bootstrap_env(plan), encoding="utf-8")
    output = tmp_path / "current.env"
    admin = RecordingConnection()
    domain_connections = []

    def connect(**kwargs):
        if kwargs["user"] == "root@capability_test":
            return admin
        connection = GrantConnection(user=kwargs["user"], database=kwargs["database"])
        domain_connections.append(connection)
        return connection

    assert main(
        [
            "--admin-url-env",
            "AI00_RC_ADMIN_DB_URL",
            "--environment-id",
            plan.environment_id,
            "--output-env",
            str(output),
            "--reuse-env",
            str(reuse_path),
        ],
        environ={
            "AI00_RC_ADMIN_DB_URL": (
                "mysql://root%40capability_test:admin-secret@127.0.0.1:2881/oceanbase"
            )
        },
        connect=connect,
        protect_file=lambda _path: None,
    ) == 0

    captured = capsys.readouterr()
    assert '"status": "reused"' in captured.out
    assert "admin-secret" not in captured.out + captured.err
    assert admin.mutations == []
    assert len(domain_connections) == 22
    assert _env_document(output.read_text(encoding="utf-8")) == _env_document(
        reuse_path.read_text(encoding="utf-8")
    )


def test_windows_file_protection_uses_exact_path_current_user_and_system(tmp_path):
    target = tmp_path / "capability-v2-rc.env"
    target.write_text("safe=test\n", encoding="utf-8")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0})()

    bootstrap_cli._protect_file(
        target,
        platform_name="nt",
        username="rc-runner",
        run=run,
    )

    assert calls == [
        (
            [
                "icacls",
                str(target),
                "/inheritance:r",
                "/grant:r",
                "rc-runner:F",
                "SYSTEM:F",
            ],
            {"text": True, "capture_output": True, "check": False},
        )
    ]
