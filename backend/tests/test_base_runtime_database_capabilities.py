import json

from backend.base import runtime_database_config
from backend.capabilities.registry_next import CapabilityRegistry


def test_password_resolution_reuses_blank_and_masked_values() -> None:
    existing = {"password": "saved-secret"}
    assert runtime_database_config.resolve_password("", existing) == "saved-secret"
    assert runtime_database_config.resolve_password("   ", existing) == "saved-secret"
    assert runtime_database_config.resolve_password("●●●●", existing) == "saved-secret"
    assert runtime_database_config.resolve_password("new-secret", existing) == "new-secret"


def test_read_never_returns_password(monkeypatch, tmp_path) -> None:
    path = tmp_path / "system.json"
    path.write_text(json.dumps({"cloud_db_config": {
        "host": "db.internal", "port": 3306, "user": "worker", "password": "secret",
        "collab_db": "craft", "public_db": "public",
    }}), encoding="utf-8")
    monkeypatch.setattr(runtime_database_config, "system_json_path", lambda: path)

    result = runtime_database_config.get_database_config({}, object())

    assert result["password_configured"] is True
    assert "password" not in result
    assert "secret" not in str(result)


def test_read_and_connection_support_legacy_uppercase_config(monkeypatch, tmp_path) -> None:
    path = tmp_path / "system.json"
    path.write_text(json.dumps({"CLOUD_DB_CONFIG": {
        "host": "legacy.internal", "port": 3307, "user": "legacy", "password": "legacy-secret",
        "collab_db": "craft", "public_db": "public",
    }}), encoding="utf-8")
    monkeypatch.setattr(runtime_database_config, "system_json_path", lambda: path)

    result = runtime_database_config.get_database_config({}, object())

    assert result["host"] == "legacy.internal"
    assert result["password_configured"] is True
    assert runtime_database_config._stored_database_config()["password"] == "legacy-secret"


def test_save_reuses_password_and_rebuilds_encoded_url(monkeypatch, tmp_path) -> None:
    path = tmp_path / "system.json"
    path.write_text(json.dumps({"cloud_db_config": {"password": "s+aved"}}), encoding="utf-8")
    monkeypatch.setattr(runtime_database_config, "system_json_path", lambda: path)

    result = runtime_database_config.save_database_config({
        "host": "db.internal", "port": 2883, "user": "user@tenant", "password": "●●●●",
        "collab_db": "craft db", "public_db": "public",
    }, object())

    saved = json.loads(path.read_text(encoding="utf-8"))["cloud_db_config"]
    assert saved["password"] == "s+aved"
    assert saved["users_db_url"] == "mysql://user%40tenant:s%2Baved@db.internal:2883/craft%20db"
    assert result == {"saved": True, "password_configured": True}


def test_connection_test_reuses_saved_password(monkeypatch) -> None:
    monkeypatch.setattr(runtime_database_config, "load_system_json", lambda: {"cloud_db_config": {"password": "saved"}})
    captured = {}

    class _Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def execute(self, sql): captured["sql"] = sql
        def fetchone(self): return {"ok": 1}

    class _Connection:
        def cursor(self): return _Cursor()
        def close(self): captured["closed"] = True

    def connect(**kwargs):
        captured.update(kwargs)
        return _Connection()

    monkeypatch.setattr(runtime_database_config.pymysql, "connect", connect)

    result = runtime_database_config.test_database_connection({
        "host": "db.internal", "port": 2883, "user": "worker", "password": "",
        "collab_db": "craft", "public_db": "public",
    }, object())

    assert result == {"connected": True}
    assert captured["password"] == "saved"
    assert captured["closed"] is True


def test_base_registers_three_atomic_runtime_database_capabilities() -> None:
    registry = CapabilityRegistry()
    runtime_database_config.register_runtime_database_capabilities(registry)

    ids = {spec.id for spec in registry.list()}
    assert ids == {
        "base.runtime.database_config.get",
        "base.runtime.database_config.change.apply",
        "base.runtime.database_connection.test",
    }
    for spec in registry.list():
        assert spec.owner == "base"
        assert spec.permissions == ("system.tech_config",)
        assert spec.plugin_callable is False
