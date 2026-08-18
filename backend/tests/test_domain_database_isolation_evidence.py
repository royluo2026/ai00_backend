from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

import pytest

from backend.capability_v2.domain_database import DomainDatabaseConfigurationError
from backend.capability_v2.database_isolation import (
    DatabaseIsolationError,
    load_probe_targets,
    verify_database_grants,
)
from backend.scripts.verify_domain_database_isolation import main


ROOT = Path(__file__).resolve().parents[2]


def test_cli_is_directly_executable_from_repository_root():
    result = subprocess.run(
        [
            sys.executable,
            "backend/scripts/verify_domain_database_isolation.py",
            "--help",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--provider-evidence" in result.stdout
    assert "--output" in result.stdout


class DatabaseDenied(Exception):
    pass


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.connection.queries.append(sql)
        if self.connection.deny:
            raise DatabaseDenied(1142, "denied")
        if sql.startswith("CREATE TABLE") and self.connection.deny_ddl:
            raise DatabaseDenied(1142, "ddl denied")
        if sql.startswith("SHOW COLUMNS"):
            self._row = ("gid",)

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self.connection.ledger_rows


class Connection:
    def __init__(self, *, deny=False, deny_ddl=True, ledger_rows=()):
        self.deny = deny
        self.deny_ddl = deny_ddl
        self.ledger_rows = tuple(ledger_rows)
        self.queries = []
        self.closed = False
        self.rolled_back = False

    def cursor(self):
        return Cursor(self)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _environment(targets):
    environment = {
        target.runtime_url_env: (
            f"mysql://{target.domain_id}_runtime:secret@db.example:2881/"
            f"{target.database_name}"
        )
        for target in targets
    }
    environment.update(
        {
            target.ddl_url_env: (
                f"mysql://{target.domain_id}_ddl:secret@db.example:2881/"
                f"{target.database_name}"
            )
            for target in targets
        }
    )
    return environment


def _ledger_rows(target):
    return tuple(
        {
            "migration_id": migration.migration_id,
            "name": migration.filename.removeprefix(f"{migration.migration_id}_").removesuffix(".sql"),
            "checksum": migration.checksum,
            "artifact_version": migration.artifact_version,
        }
        for migration in target.migrations
    )


def test_probe_targets_cover_exactly_eleven_manifest_domains_with_owned_tables():
    targets = load_probe_targets(ROOT)

    assert len(targets) == 11
    assert len({target.domain_id for target in targets}) == 11
    assert all(target.table_name.startswith("workmanship_") for target in targets)


def test_probe_targets_bind_each_ddl_credential_and_all_frozen_migrations():
    targets = load_probe_targets(ROOT)

    assert all(target.ddl_url_env.startswith("AI00_") for target in targets)
    assert sum(len(target.migrations) for target in targets) == 15
    assert {
        (target.domain_id, migration.migration_id, migration.filename)
        for target in targets
        for migration in target.migrations
    } >= {
        ("base", "0002", "0002_domain_inbox.sql"),
        ("knowledge", "0003", "0003_display_counters.sql"),
    }


def test_grant_probe_proves_owner_access_and_all_110_cross_domain_denials():
    targets = load_probe_targets(ROOT)
    targets_by_domain = {target.domain_id: target for target in targets}
    connections = []

    def connect(url, _ca_path):
        principal = url.username
        if principal.endswith("_ddl"):
            domain_id = principal.removesuffix("_ddl")
            connection = Connection(
                deny_ddl=False,
                ledger_rows=_ledger_rows(targets_by_domain[domain_id])
            )
        else:
            connection = Connection(
                deny=principal.removesuffix("_runtime")
                != url.database.removeprefix("ai00_")
            )
        connections.append(connection)
        return connection

    result = verify_database_grants(
        targets,
        _environment(targets),
        ca_path="ca.pem",
        connect=connect,
    )

    assert set(result["owner_operations"]) == {target.domain_id for target in targets}
    assert all(row["database_read"] == "passed" for row in result["owner_operations"].values())
    assert all(row["database_write"] == "passed" for row in result["owner_operations"].values())
    assert all(row["runtime_ddl"] == "denied" for row in result["owner_operations"].values())
    assert len(result["cross_domain"]) == 110
    assert all(row["read"] == row["write"] == "denied" for row in result["cross_domain"])
    assert all(connection.closed for connection in connections)


def test_grant_probe_requires_exact_live_migration_ledgers():
    targets = load_probe_targets(ROOT)
    targets_by_domain = {target.domain_id: target for target in targets}

    def connect(url, _ca_path):
        principal = url.username
        if principal.endswith("_ddl"):
            domain_id = principal.removesuffix("_ddl")
            return Connection(
                deny_ddl=False,
                ledger_rows=_ledger_rows(targets_by_domain[domain_id]),
            )
        return Connection(
            deny=principal.removesuffix("_runtime")
            != url.database.removeprefix("ai00_")
        )

    result = verify_database_grants(
        targets,
        _environment(targets),
        ca_path="ca.pem",
        connect=connect,
    )

    assert all(
        row["migration_ledger"] == "passed"
        for row in result["owner_operations"].values()
    )


def test_grant_probe_fails_if_any_cross_domain_query_is_allowed():
    targets = load_probe_targets(ROOT)
    targets_by_domain = {target.domain_id: target for target in targets}

    def connect(url, _ca_path):
        if url.username.endswith("_ddl"):
            domain_id = url.username.removesuffix("_ddl")
            return Connection(
                deny_ddl=False,
                ledger_rows=_ledger_rows(targets_by_domain[domain_id]),
            )
        return Connection(deny=False)

    with pytest.raises(DatabaseIsolationError, match="cross_domain_read_allowed"):
        verify_database_grants(
            targets,
            _environment(targets),
            ca_path="ca.pem",
            connect=connect,
        )


def test_grant_probe_does_not_misreport_unexpected_database_errors_as_denial():
    targets = load_probe_targets(ROOT)
    targets_by_domain = {target.domain_id: target for target in targets}

    def connect(url, _ca_path):
        if url.username.endswith("_ddl"):
            domain_id = url.username.removesuffix("_ddl")
            return Connection(
                deny_ddl=False,
                ledger_rows=_ledger_rows(targets_by_domain[domain_id]),
            )
        raise RuntimeError("network unavailable")

    with pytest.raises(DatabaseIsolationError, match="owner_probe_failed"):
        verify_database_grants(
            targets,
            _environment(targets),
            ca_path="ca.pem",
            connect=connect,
        )


def test_grant_probe_rejects_missing_or_changed_live_migration_rows():
    targets = load_probe_targets(ROOT)
    targets_by_domain = {target.domain_id: target for target in targets}

    def connect(url, _ca_path):
        principal = url.username
        if principal.endswith("_ddl"):
            domain_id = principal.removesuffix("_ddl")
            rows = _ledger_rows(targets_by_domain[domain_id])
            if domain_id == "agent":
                rows = ()
            return Connection(deny_ddl=False, ledger_rows=rows)
        return Connection(deny=False)

    with pytest.raises(DatabaseIsolationError, match="migration_ledger_mismatch:agent"):
        verify_database_grants(
            targets,
            _environment(targets),
            ca_path="ca.pem",
            connect=connect,
        )


def test_grant_probe_rejects_shared_runtime_and_ddl_credentials_before_connecting():
    targets = load_probe_targets(ROOT)
    environment = _environment(targets)
    agent = next(target for target in targets if target.domain_id == "agent")
    environment[agent.ddl_url_env] = environment[agent.runtime_url_env]

    with pytest.raises(
        DomainDatabaseConfigurationError,
        match="credential_separation_required",
    ):
        verify_database_grants(
            targets,
            environment,
            ca_path="ca.pem",
            connect=lambda *_args: pytest.fail("must reject before connecting"),
        )


def test_cli_binds_provider_crud_and_writes_complete_rc_fragment(tmp_path):
    targets = load_probe_targets(ROOT)
    commit = "a" * 40
    provider_path = tmp_path / "provider-crud.json"
    provider_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "environment_id": "rc-42",
                "run_id": "run-42",
                "git_commit": commit,
                "domains": {target.domain_id: "passed" for target in targets},
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "database-isolation.json"

    def connect(url, _ca_path):
        if url.username.endswith("_ddl"):
            domain_id = url.username.removesuffix("_ddl")
            target = next(item for item in targets if item.domain_id == domain_id)
            return Connection(deny_ddl=False, ledger_rows=_ledger_rows(target))
        return Connection(
            deny=url.username.removesuffix("_runtime")
            != url.database.removeprefix("ai00_")
        )

    result = main(
        ["--provider-evidence", str(provider_path), "--output", str(output_path)],
        root=ROOT,
        environ={
            **_environment(targets),
            "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-42",
            "AI00_ACCEPTANCE_RUN_ID": "run-42",
            "AI00_ACCEPTANCE_OCEANBASE_SSL_CA": "ca.pem",
        },
        connect=connect,
        git_commit=lambda: commit,
    )

    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == 0
    assert document["database_isolation"]["owner_operations"]["agent"] == {
        "provider_crud": "passed",
        "migration_ledger": "passed",
        "database_read": "passed",
        "database_write": "passed",
        "runtime_ddl": "denied",
    }
    assert len(document["database_isolation"]["cross_domain"]) == 110


def test_grant_probe_cleans_up_and_fails_if_runtime_ddl_is_allowed():
    targets = load_probe_targets(ROOT)
    targets_by_domain = {target.domain_id: target for target in targets}
    ddl_connections = []

    def connect(url, _ca_path):
        principal = url.username
        if principal.endswith("_ddl"):
            domain_id = principal.removesuffix("_ddl")
            connection = Connection(
                deny_ddl=False,
                ledger_rows=_ledger_rows(targets_by_domain[domain_id]),
            )
            ddl_connections.append((domain_id, connection))
            return connection
        domain_id = principal.removesuffix("_runtime")
        return Connection(
            deny=domain_id != url.database.removeprefix("ai00_"),
            deny_ddl=domain_id != "agent",
        )

    with pytest.raises(DatabaseIsolationError, match="runtime_ddl_allowed:agent"):
        verify_database_grants(
            targets,
            _environment(targets),
            ca_path="ca.pem",
            connect=connect,
        )

    agent_ddl_queries = [
        sql
        for domain_id, connection in ddl_connections
        if domain_id == "agent"
        for sql in connection.queries
    ]
    assert any(sql.startswith("DROP TABLE IF EXISTS") for sql in agent_ddl_queries)
