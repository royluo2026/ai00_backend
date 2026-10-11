import stat
from types import SimpleNamespace

import pymysql
import pytest

from backend.db.table_prefix import configure_table_prefix
from backend.scripts import run_migrations
from backend.db.versioned_migrations import apply_migrations


class Cursor:
    def __init__(self):
        self.query = None

    def execute(self, query, args=None):
        self.query = query


class Connection:
    def __init__(self):
        self.created = []

    def cursor(self):
        cursor = Cursor()
        self.created.append(cursor)
        return cursor

    def close(self):
        pass


def test_migration_entrypoint_wraps_ddl_connection_with_table_prefix(monkeypatch):
    configure_table_prefix("")
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.setenv("TABLE_PREFIX", "test_")
    monkeypatch.setenv("AI00_DDL_DB_URL", "mysql://ddl:secret@db.example/ai00")
    connection = Connection()
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: connection)
    monkeypatch.setattr(
        run_migrations,
        "verify_live_server",
        lambda conn: {"version": "test", "compatibility_mode": "MYSQL"},
    )

    def probe_prefix(conn, path):
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE workmanship_probe (id BIGINT)")
        return False

    monkeypatch.setattr(run_migrations, "apply_bootstrap_schema", probe_prefix)
    monkeypatch.setattr(run_migrations, "apply_migrations", lambda conn: [])

    try:
        assert run_migrations.main() == 0
        assert connection.created[0].query == "CREATE TABLE test_workmanship_probe (id BIGINT)"
    finally:
        configure_table_prefix("")


def test_base_migration_runner_handles_oceanbase_without_named_locks(tmp_path):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, query, args=None):
            if "GET_LOCK" in query:
                raise RuntimeError(1305, "FUNCTION GET_LOCK does not exist")
        def fetchall(self): return []

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass

    assert apply_migrations(Connection(), directory=tmp_path, registry=object()) == []


@pytest.mark.parametrize(("profile", "prefix", "url"), [
    ("production", "test_", "https://workmanship-backend.chehejia.com"),
    ("test", "pp_", "http://127.0.0.1:8080"),
    ("", "pp_", "https://workmanship-backend.chehejia.com"),
])
def test_migration_refuses_wrong_profile_before_connection(monkeypatch, profile, prefix, url):
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.setenv("AI00_DDL_DB_URL", "mysql://ddl:secret@db.example/ai00")
    monkeypatch.setenv("AI00_DEPLOY_PROFILE", profile)
    monkeypatch.setenv("TABLE_PREFIX", prefix)
    monkeypatch.setenv("PUBLIC_URL", url)
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    with pytest.raises(SystemExit, match="profile|ENV_FILE|prefix"):
        run_migrations.main()


def test_migration_env_file_cannot_inherit_production_profile(monkeypatch, tmp_path):
    env_file = tmp_path / "migration.env"
    env_file.write_text(
        "TABLE_PREFIX=pp_\nPUBLIC_URL=https://workmanship-backend.chehejia.com\n"
        "AI00_DDL_DB_URL=mysql://ddl:secret@db.example/ai00\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.setenv("AI00_DEPLOY_PROFILE", "production")
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    with pytest.raises(SystemExit, match="managed_deployment_requires_explicit_profile"):
        run_migrations.main()


@pytest.mark.parametrize("key,other", [
    ("AI00_DEPLOY_PROFILE", "production"), ("TABLE_PREFIX", "pp_"),
    ("AI00_DDL_DB_URL", "mysql://other:secret@db.example/workmanship"),
    ("AI00_REQUIRE_MIGRATIONS", "1"),
])
def test_base_migration_refuses_duplicate_managed_env_before_connection(monkeypatch, tmp_path, key, other):
    env_file = tmp_path / "migration.env"
    env_file.write_text("AI00_DEPLOY_PROFILE=test\nTABLE_PREFIX=test_\n"
                        "PUBLIC_URL=http://127.0.0.1:8080\n"
                        "AI00_DDL_DB_URL=mysql://ddl:secret@db.example/workmanship\n"
                        "AI00_REQUIRE_MIGRATIONS=0\n"
                        f"{key}={other}\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    with pytest.raises(SystemExit, match="duplicate"):
        run_migrations.main()


def test_base_migration_refuses_linked_managed_env_before_connection(monkeypatch, tmp_path):
    env_file = tmp_path / "migration.env"
    env_file.write_text("AI00_DEPLOY_PROFILE=test", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_file))
    original = type(env_file).lstat
    monkeypatch.setattr(type(env_file), "lstat", lambda path: SimpleNamespace(st_mode=stat.S_IFLNK)
                        if path == env_file else original(path))
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: pytest.fail("database connection attempted"))
    with pytest.raises(SystemExit, match="missing or invalid"):
        run_migrations.main()
