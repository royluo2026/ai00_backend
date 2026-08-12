from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

import pytest

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
        if sql.startswith("SHOW COLUMNS"):
            self._row = ("gid",)

    def fetchone(self):
        return self._row


class Connection:
    def __init__(self, *, deny=False):
        self.deny = deny
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
    return {
        target.runtime_url_env: (
            f"mysql://{target.domain_id}_runtime:secret@db.example:2881/"
            f"{target.database_name}"
        )
        for target in targets
    }


def test_probe_targets_cover_exactly_eleven_manifest_domains_with_owned_tables():
    targets = load_probe_targets(ROOT)

    assert len(targets) == 11
    assert len({target.domain_id for target in targets}) == 11
    assert all(target.table_name.startswith("workmanship_") for target in targets)


def test_grant_probe_proves_owner_access_and_all_110_cross_domain_denials():
    targets = load_probe_targets(ROOT)
    connections = []

    def connect(url, _ca_path):
        connection = Connection(
            deny=url.username.removesuffix("_runtime")
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
    assert len(result["cross_domain"]) == 110
    assert all(row["read"] == row["write"] == "denied" for row in result["cross_domain"])
    assert all(connection.closed for connection in connections)


def test_grant_probe_fails_if_any_cross_domain_query_is_allowed():
    targets = load_probe_targets(ROOT)

    with pytest.raises(DatabaseIsolationError, match="cross_domain_read_allowed"):
        verify_database_grants(
            targets,
            _environment(targets),
            ca_path="ca.pem",
            connect=lambda _url, _ca_path: Connection(deny=False),
        )


def test_grant_probe_does_not_misreport_unexpected_database_errors_as_denial():
    targets = load_probe_targets(ROOT)

    def connect(_url, _ca_path):
        raise RuntimeError("network unavailable")

    with pytest.raises(DatabaseIsolationError, match="owner_probe_failed"):
        verify_database_grants(
            targets,
            _environment(targets),
            ca_path="ca.pem",
            connect=connect,
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
        "database_read": "passed",
        "database_write": "passed",
    }
    assert len(document["database_isolation"]["cross_domain"]) == 110
