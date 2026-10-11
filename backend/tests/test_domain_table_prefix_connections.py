import importlib

import pytest

from backend.db.prefixed_cursor import wrap_connection
from backend.db.table_prefix import configure_table_prefix


DOMAIN_CONNECTIONS = (
    ("plugins.ontology.ontology_backend.infrastructure.connection", "get_ontology_conn"),
    ("plugins.agent.agent_backend.data.connection", "get_agent_conn"),
    ("plugins.digital_model.digital_model_backend.data.connection", "get_digital_model_conn"),
    ("plugins.knowledge.knowledge_backend.data.connection", "get_knowledge_conn"),
    ("plugins.factory.factory_backend.infrastructure.connection", "get_factory_conn"),
    ("plugins.craft.craft_backend.data.connection", "get_craft_conn"),
    (
        "plugins.project_management.project_management_backend.data.connection",
        "get_project_management_conn",
    ),
    ("plugins.simulation.simulation_backend.data.connection", "get_simulation_conn"),
    ("plugins.integration.integration_backend.data.connection", "get_integration_conn"),
    ("plugins.device.device_backend.data.connection", "get_device_conn"),
)


class Cursor:
    def __init__(self):
        self.query = None

    def execute(self, query, args=None):
        self.query = query

    def fetchone(self):
        return None


class Connection:
    def __init__(self):
        self.created = []

    def begin(self):
        pass

    def cursor(self):
        cursor = Cursor()
        self.created.append(cursor)
        return cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class Pool:
    def __init__(self, connection):
        self._connection = connection

    def connection(self):
        return self._connection


@pytest.fixture(autouse=True)
def reset_table_prefix():
    configure_table_prefix("")
    yield
    configure_table_prefix("")


def test_wrap_connection_rewrites_once():
    configure_table_prefix("test_")
    raw = Connection()
    connection = wrap_connection(raw)
    assert connection is not raw
    assert wrap_connection(connection) is connection
    assert raw.cursor.__func__ is Connection.cursor
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM workmanship_proj_projects")
    assert cursor._inner.query == "SELECT * FROM test_workmanship_proj_projects"


def test_prefixed_connection_does_not_expose_unrewritten_sql_methods():
    configure_table_prefix("pp_")
    raw = Connection()
    raw.query = lambda sql: sql
    connection = wrap_connection(raw)
    cursor = connection.cursor()
    cursor._inner.callproc = lambda name: name
    with pytest.raises(AttributeError):
        connection.query("SELECT * FROM workmanship_auth_users")
    with pytest.raises(AttributeError):
        cursor.callproc("unreviewed_procedure")
    connection.begin()
    connection.commit()
    connection.rollback()


def test_prefix_is_bound_to_acquisition_and_old_pool_handles_are_invalidated():
    configure_table_prefix("test_")
    raw = Connection()
    connection = wrap_connection(raw)
    cursor = connection.cursor()
    configure_table_prefix("pp_")
    cursor.execute("SELECT * FROM workmanship_proj_projects")
    assert cursor._inner.query == "SELECT * FROM test_workmanship_proj_projects"
    next_cursor = connection.cursor()
    next_cursor.execute("SELECT * FROM workmanship_proj_projects")
    assert next_cursor._inner.query == "SELECT * FROM test_workmanship_proj_projects"
    with pytest.raises(ValueError, match="prefix"):
        wrap_connection(connection)
    connection.close()
    with pytest.raises(RuntimeError, match="closed"):
        cursor.execute("SELECT * FROM workmanship_proj_projects")
    with pytest.raises(RuntimeError, match="closed"):
        next_cursor.fetchone()
    with pytest.raises(RuntimeError, match="closed"):
        connection.cursor()
    with pytest.raises(RuntimeError, match="closed"):
        wrap_connection(connection)
    reused = wrap_connection(raw)
    reused.cursor().execute("SELECT * FROM workmanship_proj_projects")
    assert raw.created[-1].query == "SELECT * FROM pp_workmanship_proj_projects"


def test_base_pool_context_uses_a_fresh_bound_wrapper_on_reuse(monkeypatch):
    from backend.db import connection as base

    raw = Connection()
    monkeypatch.setattr(base, "_pool", Pool(raw))
    configure_table_prefix("test_")
    with base.get_conn() as first:
        old_cursor = first.cursor()
        old_cursor.execute("SELECT * FROM workmanship_auth_users")
        configure_table_prefix("pp_")
        first.cursor().execute("SELECT * FROM workmanship_auth_users")
        assert raw.created[-1].query == "SELECT * FROM test_workmanship_auth_users"
    with pytest.raises(RuntimeError, match="closed"):
        old_cursor.execute("SELECT * FROM workmanship_auth_users")
    with base.get_conn() as second:
        second.cursor().execute("SELECT * FROM workmanship_auth_users")
        assert raw.created[-1].query == "SELECT * FROM pp_workmanship_auth_users"
    assert raw.cursor.__func__ is Connection.cursor


def test_knowledge_pool_context_invalidates_its_previous_cursor(monkeypatch):
    from backend.knowledge.data import connection as knowledge

    raw = Connection()
    monkeypatch.setattr(knowledge, "_get_pool", lambda: Pool(raw))
    configure_table_prefix("test_")
    with knowledge.get_knowledge_conn() as first:
        old_cursor = first.cursor()
        old_cursor.execute("SELECT * FROM workmanship_knowledge_items")
        configure_table_prefix("pp_")
        first.cursor().execute("SELECT * FROM workmanship_knowledge_items")
        assert raw.created[-1].query == "SELECT * FROM test_workmanship_knowledge_items"
    with pytest.raises(RuntimeError, match="closed"):
        old_cursor.fetchone()
    with knowledge.get_knowledge_conn() as second:
        second.cursor().execute("SELECT * FROM workmanship_knowledge_items")
        assert raw.created[-1].query == "SELECT * FROM pp_workmanship_knowledge_items"
    assert raw.cursor.__func__ is Connection.cursor


def test_actual_dbutils_pool_reuse_cannot_revive_an_old_prefix_cursor():
    import sqlite3
    from dbutils.pooled_db import PooledDB

    pool = PooledDB(sqlite3, maxconnections=1, mincached=1, maxcached=1,
                    database=":memory:")
    seed = pool.connection()
    seed.cursor().execute("CREATE TABLE test_workmanship_probe (marker TEXT)")
    seed.cursor().execute("CREATE TABLE pp_workmanship_probe (marker TEXT)")
    seed.cursor().execute("INSERT INTO test_workmanship_probe VALUES ('test')")
    seed.cursor().execute("INSERT INTO pp_workmanship_probe VALUES ('production')")
    seed.commit()
    seed.close()

    configure_table_prefix("test_")
    first = wrap_connection(pool.connection())
    old_cursor = first.cursor()
    old_cursor.execute("SELECT marker FROM workmanship_probe")
    assert old_cursor.fetchone() == ("test",)
    configure_table_prefix("pp_")
    first.cursor().execute("SELECT marker FROM workmanship_probe")
    first.close()
    with pytest.raises(RuntimeError, match="closed"):
        old_cursor.execute("SELECT marker FROM workmanship_probe")
    second = wrap_connection(pool.connection())
    cursor = second.cursor()
    cursor.execute("SELECT marker FROM workmanship_probe")
    assert cursor.fetchone() == ("production",)
    second.close()


def test_knowledge_outbox_poller_uses_its_domain_prefix_for_read_and_update(monkeypatch):
    module = importlib.import_module(
        "plugins.knowledge.knowledge_backend.infrastructure.domain_outbox"
    )

    class PollerCursor(Cursor):
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def fetchall(self):
            return []

    class PollerConnection(Connection):
        def cursor(self):
            cursor = PollerCursor()
            self.created.append(cursor)
            return cursor

    raw = PollerConnection()
    monkeypatch.setattr(module, "_get_pool", lambda: Pool(raw))
    configure_table_prefix("pp_")
    poller = module.KnowledgeOutboxPoller()
    assert poller.poll() == ()
    poller.mark_delivered("outbox-1")
    assert raw.created[0].query.startswith("SELECT gid,event_type,event_version,subject_ref,payload,attempts,created_at FROM pp_workmanship_know_domain_outbox ")
    assert raw.created[1].query.startswith("UPDATE pp_workmanship_know_domain_outbox SET ")


def test_domain_migration_ledger_uses_test_prefix():
    configure_table_prefix("test_")
    raw = Connection()
    connection = wrap_connection(raw)
    connection.cursor().execute("SELECT migration_id FROM ai00_simulation_schema_migrations")
    assert raw.created[-1].query == "SELECT migration_id FROM test_ai00_simulation_schema_migrations"


def test_historical_upload_trigger_uses_test_prefix():
    configure_table_prefix("test_")
    raw = Connection()
    connection = wrap_connection(raw)
    connection.cursor().execute(
        "CREATE TRIGGER base_historical_uploads_no_update BEFORE UPDATE "
        "ON workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE '45000'"
    )
    assert "CREATE TRIGGER test_base_historical_uploads_no_update" in raw.created[-1].query
    assert "ON test_workmanship_base_historical_uploads" in raw.created[-1].query


@pytest.mark.parametrize(("module_name", "context_name"), DOMAIN_CONNECTIONS)
def test_domain_connection_rewrites_sql(monkeypatch, module_name, context_name):
    configure_table_prefix("test_")
    module = importlib.import_module(module_name)
    connection = Connection()
    monkeypatch.setattr(module, "_get_pool", lambda: Pool(connection))

    with getattr(module, context_name)() as acquired:
        cursor = acquired.cursor()
        cursor.execute("SELECT * FROM workmanship_probe")

    assert cursor._inner.query == "SELECT * FROM test_workmanship_probe"


def test_agent_transaction_connection_rewrites_sql(monkeypatch):
    configure_table_prefix("test_")
    module = importlib.import_module("plugins.agent.agent_backend.data.connection")
    connection = Connection()
    monkeypatch.setattr(module, "_get_pool", lambda: Pool(connection))

    transaction = module.begin_agent_transaction()
    try:
        cursor = transaction.connection().cursor()
        cursor.execute("SELECT * FROM workmanship_probe")
    finally:
        module.close_agent_transaction(transaction)

    assert cursor._inner.query == "SELECT * FROM test_workmanship_probe"
