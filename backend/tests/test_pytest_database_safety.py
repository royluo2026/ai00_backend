import importlib
import os


def test_pytest_suite_enables_offline_database_mode_by_default():
    assert os.getenv("AI00_PYTEST_OFFLINE") == "1"


def test_offline_mode_never_constructs_base_connection_pool(monkeypatch):
    connection = importlib.import_module("backend.db.connection")
    calls = []
    monkeypatch.setattr(connection, "_pool", None)
    monkeypatch.setenv("AI00_PYTEST_OFFLINE", "1")
    monkeypatch.delenv("AI00_ALLOW_LIVE_DB_TESTS", raising=False)
    monkeypatch.setattr(connection, "PooledDB", lambda **kwargs: calls.append(kwargs))

    connection.init_pool()

    assert connection._pool is None
    assert calls == []


def test_live_database_tests_require_explicit_opt_in(monkeypatch):
    connection = importlib.import_module("backend.db.connection")
    sentinel = object()
    monkeypatch.setattr(connection, "_pool", None)
    monkeypatch.setenv("AI00_PYTEST_OFFLINE", "1")
    monkeypatch.setenv("AI00_ALLOW_LIVE_DB_TESTS", "1")
    monkeypatch.setattr(connection, "PooledDB", lambda **_kwargs: sentinel)
    monkeypatch.setattr(
        connection,
        "get_settings",
        lambda: type("Settings", (), {"get_db_params": lambda self: {
            "host": "test", "port": 3306, "user": "test", "password": "test", "db": "test",
        }})(),
    )

    connection.init_pool()

    assert connection._pool is sentinel
