import json
import sys
from pathlib import Path

import pytest

from backend.scripts.runtime_preflight import REQUIRED_DB_URLS
from backend.scripts.verify_domain_db_isolation import URLS, verify
from backend.scripts import verify_domain_db_isolation as probe_module


INVENTORY = Path(__file__).resolve().parents[1] / "governance/table_inventory.json"


def profile_environment(prefix="test_", profile="test"):
    values = {variable: f"mysql://account_{index}:secret@db.example:2881/workmanship"
              for index, variable in enumerate(REQUIRED_DB_URLS)}
    values.update({"TABLE_PREFIX": prefix, "AI00_DEPLOY_PROFILE": profile,
                   "PUBLIC_URL": "https://workmanship-backend.chehejia.com" if profile == "production"
                                 else "http://127.0.0.1:8080"})
    return values


def test_isolation_probe_covers_all_official_runtime_accounts():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert set(URLS.values()) == set(REQUIRED_DB_URLS)
    assert set(URLS) == {item["runtime_domain"] for item in inventory["tables"]}


@pytest.mark.parametrize(("prefix", "profile"), [
    ("", "test"), ("test_", "production"), ("pp_", "test"), ("other_", "test"),
    ("test_", ""),
 ])
def test_wrong_or_missing_prefix_profile_never_connects(monkeypatch, prefix, profile):
    import pymysql
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    with pytest.raises(ValueError, match="prefix|profile"):
        verify(INVENTORY, env=profile_environment(prefix, profile))


def test_missing_account_does_not_probe_any_other_account(monkeypatch):
    import pymysql
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    environment = profile_environment()
    environment.pop("AI00_FACTORY_DB_URL")
    results = verify(INVENTORY, env=environment)
    assert any(not item.ok and item.target == "AI00_FACTORY_DB_URL" for item in results)


def test_legacy_local_integration_identity_requires_owner_mapping(monkeypatch):
    import pymysql
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    environment = profile_environment()
    environment["AI00_LOCAL_INTEGRATION_DB_URL"] = "mysql://legacy:secret@db.example:2881/workmanship"
    results = verify(INVENTORY, env=environment)
    assert any(not item.ok and item.check == "account-coverage-unverified" for item in results)


def test_isolation_probe_does_not_consume_ambient_database_credentials():
    with pytest.raises(ValueError, match="explicit environment file"):
        verify(INVENTORY)


def test_isolation_cli_refuses_duplicate_env_before_probe(monkeypatch, tmp_path):
    env_file = tmp_path / "profile.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in
                                  profile_environment().items()) +
                        "\nAI00_REQUIRE_MIGRATIONS=0\nAI00_REQUIRE_MIGRATIONS=0\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["verify_domain_db_isolation.py", "--env-file", str(env_file)])
    monkeypatch.setattr(probe_module, "verify", lambda *_args, **_kwargs: pytest.fail("probe attempted"))
    with pytest.raises(SystemExit, match="duplicate"):
        probe_module.main()


def test_isolation_cli_refuses_linked_env_before_probe(monkeypatch, tmp_path):
    env_file = tmp_path / "profile.env"
    env_file.write_text("AI00_DEPLOY_PROFILE=test", encoding="utf-8")
    import stat
    from types import SimpleNamespace
    original = type(env_file).lstat
    monkeypatch.setattr(type(env_file), "lstat", lambda path: SimpleNamespace(st_mode=stat.S_IFLNK, st_size=1) if path == env_file else original(path))
    monkeypatch.setattr(sys, "argv", ["verify_domain_db_isolation.py", "--env-file", str(env_file)])
    monkeypatch.setattr(probe_module, "verify", lambda *_args, **_kwargs: pytest.fail("probe attempted"))
    with pytest.raises(SystemExit, match="missing or invalid"):
        probe_module.main()


@pytest.mark.parametrize(("variable", "replacement", "check"), [
    ("AI00_FACTORY_DB_URL", "mysql://account_9:secret@other.example:2881/workmanship", "target-mismatch"),
])
def test_mismatched_target_stops_before_probe(monkeypatch, variable, replacement, check):
    import pymysql
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    environment = profile_environment()
    environment[variable] = replacement
    results = verify(INVENTORY, env=environment)
    assert any(not item.ok and item.check == check for item in results)


def test_unsafe_database_identifier_stops_before_connection(monkeypatch):
    import pymysql
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    environment = profile_environment()
    environment["AI00_FACTORY_DB_URL"] = "mysql://factory:secret@db.example:2881/workmanship%60other"
    with pytest.raises(ValueError, match="invalid runtime database URL"):
        verify(INVENTORY, env=environment)


@pytest.mark.parametrize("unexpected_grant", [False, True])
def test_all_domains_probe_owned_foreign_and_opposite_prefix_tables(monkeypatch, unexpected_grant):
    import pymysql

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    owners = {row["table"]: row["runtime_domain"] for row in inventory["tables"]}
    domain_by_user = {f"account_{index}": domain for domain, variable in URLS.items()
                      for index, required in enumerate(REQUIRED_DB_URLS) if variable == required}
    statements = []

    class Denied(Exception):
        pass

    class Cursor:
        def __init__(self, domain):
            self.domain = domain

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            statements.append(sql)
            table = sql.split("`")[-2]
            if table.startswith("pp_"):
                if unexpected_grant and self.domain == "base" and table == "pp_workmanship_agent_canvas_audit_events":
                    return 0
                raise Denied(1142, "denied")
            if owners[table.removeprefix("test_")] != self.domain:
                raise Denied(1142, "denied")
            return 0

    class Connection:
        def __init__(self, domain):
            self.domain = domain

        def cursor(self):
            return Cursor(self.domain)

        def close(self):
            pass

    monkeypatch.setattr(pymysql, "connect", lambda **params: Connection(domain_by_user[params["user"]]))
    results = verify(INVENTORY, env=profile_environment())
    assert len(results) == len(URLS) * (1 + 2 * len(owners))
    assert all(statement.startswith("SELECT 1 FROM `workmanship`.`") for statement in statements)
    assert all("WHERE 1=0" in statement for statement in statements)
    if unexpected_grant:
        assert any(not item.ok and item.check == "cross-prefix-deny" for item in results)
    else:
        assert all(item.ok for item in results)


@pytest.mark.parametrize(("prefix", "profile"), [("test_", "test"), ("pp_", "production")])
@pytest.mark.parametrize("unexpected_grant", [False, True])
def test_write_denial_probe_is_opt_in_zero_row_and_rolls_back(monkeypatch, prefix, profile, unexpected_grant):
    import pymysql

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    owners = {row["table"]: row["runtime_domain"] for row in inventory["tables"]}
    domain_by_user = {f"account_{index}": domain for domain, variable in URLS.items()
                      for index, required in enumerate(REQUIRED_DB_URLS) if variable == required}
    connections = []
    statements = []
    opposite = "pp_" if prefix == "test_" else "test_"

    class Denied(Exception):
        pass

    class Cursor:
        def __init__(self, domain):
            self.domain = domain

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            statements.append(sql)
            table = sql.split("`")[-2]
            if sql.startswith("DELETE"):
                if (unexpected_grant and self.domain == "base" and
                        table == opposite + "workmanship_agent_canvas_audit_events"):
                    return 0
                raise Denied(1142, "denied")
            if table.startswith(opposite) or owners[table.removeprefix(prefix)] != self.domain:
                raise Denied(1142, "denied")
            return 0

    class Connection:
        def __init__(self, domain):
            self.domain = domain
            self.rollbacks = 0

        def cursor(self):
            return Cursor(self.domain)

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    def connect(**params):
        connection = Connection(domain_by_user[params["user"]])
        connections.append(connection)
        return connection

    monkeypatch.setattr(pymysql, "connect", connect)
    results = verify(INVENTORY, env=profile_environment(prefix, profile),
                     verify_write_denied=True)
    deletes = [statement for statement in statements if statement.startswith("DELETE")]
    assert len(deletes) == (len(URLS) * 2 - 1) * len(owners)
    assert all(statement.startswith("DELETE FROM `workmanship`.`") and
               statement.endswith(" WHERE 1=0") for statement in deletes)
    assert sum(connection.rollbacks for connection in connections) == len(deletes)
    if unexpected_grant:
        assert any(not item.ok and item.check == "cross-prefix-write-deny" for item in results)
    else:
        assert all(item.ok for item in results)


def test_write_probe_rollback_failure_stops_all_later_connections(monkeypatch):
    import pymysql

    connections = []

    class Denied(Exception):
        pass

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            if statement.startswith("SELECT") or statement.startswith("DELETE"):
                raise Denied(1142, "denied")

    class Connection:
        def cursor(self):
            return Cursor()

        def rollback(self):
            raise RuntimeError("rollback unavailable")

        def close(self):
            pass

    def connect(**_params):
        connections.append(Connection())
        return connections[-1]

    monkeypatch.setattr(pymysql, "connect", connect)
    results = verify(INVENTORY, env=profile_environment(), verify_write_denied=True)
    assert len(connections) == 1
    assert results[-1].check == "write-rollback-failed" and not results[-1].ok


def test_shared_account_probes_owned_table_union_and_reports_cross_prefix_as_observation(monkeypatch):
    import pymysql
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,sql):return 0
    class Connection:
        def cursor(self):return Cursor()
        def close(self):pass
    monkeypatch.setattr(pymysql,'connect',lambda **kwargs:Connection())
    environment=profile_environment()
    for variable in REQUIRED_DB_URLS:environment[variable]='mysql://shared:secret@db.example:2881/workmanship'
    results=verify(INVENTORY,env=environment)
    assert results and all(row.ok for row in results)
    assert any(row.check=='shared-table-allow' for row in results)
    assert any(row.check=='cross-prefix-observation' for row in results)
