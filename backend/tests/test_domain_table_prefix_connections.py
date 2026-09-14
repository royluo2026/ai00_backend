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


class Connection:
    def __init__(self):
        self.created = []

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
    connection = Connection()
    assert wrap_connection(connection) is connection
    assert wrap_connection(connection) is connection
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM workmanship_proj_projects")
    assert cursor._inner.query == "SELECT * FROM test_workmanship_proj_projects"


def test_domain_migration_ledger_uses_test_prefix():
    configure_table_prefix("test_")
    connection = wrap_connection(Connection())
    connection.cursor().execute("SELECT migration_id FROM ai00_simulation_schema_migrations")
    assert connection.created[-1].query == "SELECT migration_id FROM test_ai00_simulation_schema_migrations"


def test_historical_upload_trigger_uses_test_prefix():
    configure_table_prefix("test_")
    connection = wrap_connection(Connection())
    connection.cursor().execute(
        "CREATE TRIGGER base_historical_uploads_no_update BEFORE UPDATE "
        "ON workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE '45000'"
    )
    assert "CREATE TRIGGER test_base_historical_uploads_no_update" in connection.created[-1].query
    assert "ON test_workmanship_base_historical_uploads" in connection.created[-1].query


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
