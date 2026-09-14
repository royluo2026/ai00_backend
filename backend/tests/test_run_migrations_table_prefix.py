import pymysql

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
