from __future__ import annotations

from dataclasses import asdict
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import json

import pytest
from fastapi import HTTPException

from backend.capability_v2.metrics import CapabilityMetricRecord
from backend.capability_v2.resource_budget import MemorySnapshot
from backend.routers import health
from backend.scripts.runtime_preflight import REQUIRED_DB_URLS


class _Sampler:
    def __init__(self, ratio: float | None):
        self.ratio = ratio

    def snapshot(self):
        level = "not_ready" if self.ratio is not None and self.ratio >= 0.90 else "reject_large"
        return MemorySnapshot(
            rss_bytes=123,
            cgroup_current_bytes=None if self.ratio is None else int(self.ratio * 1000),
            cgroup_limit_bytes=None if self.ratio is None else 1000,
            ratio=self.ratio,
            level=level,
        )


@pytest.mark.parametrize(("ratio", "expected"), [(0.8999, True), (0.90, False), (None, True)])
def test_memory_readiness_changes_only_at_ninety_percent(ratio, expected):
    result = health.memory_readiness(_Sampler(ratio))
    assert result.ready is expected
    assert result.snapshot.ratio == ratio


def test_connector_signing_readiness_rejects_missing_signer(monkeypatch):
    for name in (
        "AI00_CONNECTOR_PLAN_SIGNING_P256_KEY_ID",
        "AI00_CONNECTOR_PLAN_SIGNING_P256_PRIVATE_KEY",
        "AI00_CONNECTOR_PLAN_SIGNING_P256_NOT_BEFORE",
        "AI00_CONNECTOR_PLAN_SIGNING_P256_NOT_AFTER",
    ):
        monkeypatch.delenv(name, raising=False)

    assert health.connector_signing_readiness() == "not_configured"


def test_domain_readiness_accepts_shared_account_and_requires_all_domain_urls_and_matching_profile(monkeypatch):
    for index, variable in enumerate(REQUIRED_DB_URLS):
        monkeypatch.setenv(variable, "mysql://shared:secret@db.example:2881/workmanship")
    monkeypatch.setenv("AI00_DEPLOY_PROFILE", "test")
    monkeypatch.setenv("TABLE_PREFIX", "test_")
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8080")
    assert health.domain_db_configuration() == "ok"
    monkeypatch.delenv("AI00_FACTORY_DB_URL")
    assert health.domain_db_configuration() == "invalid"
    monkeypatch.setenv("AI00_FACTORY_DB_URL", "mysql://account_9:secret@db.example:2881/workmanship")
    monkeypatch.setenv("TABLE_PREFIX", "pp_")
    assert health.domain_db_configuration() == "invalid"


def test_local_runtime_shared_database_readiness_without_managed_profile(monkeypatch):
    for variable in REQUIRED_DB_URLS:
        monkeypatch.setenv(variable, "mysql://shared:secret@db.example:2881/workmanship")
    monkeypatch.delenv("AI00_DEPLOY_PROFILE", raising=False)
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.setenv("AI00_DEPLOYMENT_PROFILE", "test-governance")
    monkeypatch.setenv("TABLE_PREFIX", "test_")
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8080")
    assert health.domain_db_configuration() == "ok"
    from backend.scripts.runtime_preflight import validate_runtime_values
    import os
    assert validate_runtime_values(os.environ)
    monkeypatch.setenv("PUBLIC_URL", "https://external.example:8080")
    assert health.domain_db_configuration() == "invalid"


def test_ready_rejects_invalid_profile_before_any_database_connection(monkeypatch):
    for index, variable in enumerate(REQUIRED_DB_URLS):
        monkeypatch.setenv(variable, f"mysql://account_{index}:secret@db.example:2881/workmanship")
    monkeypatch.setenv("AI00_DEPLOY_PROFILE", "production")
    monkeypatch.setenv("TABLE_PREFIX", "test_")
    monkeypatch.setenv("PUBLIC_URL", "https://workmanship-backend.chehejia.com")
    monkeypatch.setattr(health, "memory_readiness", lambda: SimpleNamespace(ready=True))
    monkeypatch.setattr(health, "connector_signing_readiness", lambda: "ok")
    monkeypatch.setattr("backend.db.connection.get_conn", lambda: pytest.fail("database connection attempted"))
    monkeypatch.setattr(health, "domain_db_connectivity", lambda: pytest.fail("domain probe attempted"))
    request = SimpleNamespace(app=SimpleNamespace(openapi=lambda: {"paths": {
        route: {} for route in ("/api/tasks", "/api/projects", "/api/bop/versions",
                             "/api/v1/plugin-marketplace/registry")
    }}))
    response = health.ready(request)
    assert response.status_code == 503
    assert json.loads(response.body)["checks"]["domain_db_config"] == "invalid"


def test_domain_connectivity_probes_each_account_with_select_only():
    values = {variable: f"mysql://account_{index}:secret@db.example:2881/workmanship"
              for index, variable in enumerate(REQUIRED_DB_URLS)}
    seen = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            assert sql == "SELECT 1"

    class Connection:
        def __init__(self, user):
            self.user = user

        def cursor(self):
            return Cursor()

        def close(self):
            seen.append(self.user)

    def connect(**kwargs):
        assert kwargs["connect_timeout"] <= 3
        assert kwargs["read_timeout"] <= 3
        return Connection(kwargs["user"])

    checks = health.probe_domain_db_accounts(values, connect)
    assert checks == {variable: "ok" for variable in REQUIRED_DB_URLS}
    assert set(seen) == {f"account_{index}" for index in range(len(REQUIRED_DB_URLS))}


def test_domain_connectivity_failure_is_sanitized_and_fails_ready(monkeypatch):
    values = {variable: f"mysql://account_{index}:private-secret@db.example:2881/workmanship"
              for index, variable in enumerate(REQUIRED_DB_URLS)}

    def connect(**kwargs):
        if kwargs["user"] == "account_9":
            raise RuntimeError("private-secret is unreachable")

        class Connection:
            def cursor(self):
                class Cursor:
                    def __enter__(self): return self
                    def __exit__(self, *_args): return False
                    def execute(self, sql): assert sql == "SELECT 1"
                return Cursor()
            def close(self): pass
        return Connection()

    checks = health.probe_domain_db_accounts(values, connect)
    assert checks["AI00_FACTORY_DB_URL"] == "error: RuntimeError"
    assert "private-secret" not in str(checks)
    monkeypatch.setattr(health, "domain_db_configuration", lambda: "ok")
    monkeypatch.setattr(health, "domain_db_connectivity", lambda: checks)
    monkeypatch.setattr(health, "memory_readiness", lambda: SimpleNamespace(ready=True))
    monkeypatch.setattr(health, "connector_signing_readiness", lambda: "ok")
    monkeypatch.setattr("backend.db.connection.get_conn", lambda: pytest.fail("unexpected database connection"))
    request = SimpleNamespace(app=SimpleNamespace(openapi=lambda: {"paths": {
        route: {} for route in ("/api/tasks", "/api/projects", "/api/bop/versions",
                             "/api/v1/plugin-marketplace/registry")
    }}))
    response = health.ready(request)
    assert response.status_code == 503
    assert "private-secret" not in response.body.decode("utf-8")


def test_domain_probe_cache_is_bounded_and_invalidated_on_account_change(monkeypatch):
    for index, variable in enumerate(REQUIRED_DB_URLS):
        monkeypatch.setenv(variable, f"mysql://account_{index}:secret@db.example:2881/workmanship")
    monkeypatch.setattr(health, "_domain_probe_cache", None)
    clock = [100.0]
    monkeypatch.setattr(health.time, "monotonic", lambda: clock[0])
    calls = []

    def probe(values):
        calls.append(values["AI00_FACTORY_DB_URL"])
        return {variable: "ok" for variable in REQUIRED_DB_URLS}

    monkeypatch.setattr(health, "probe_domain_db_accounts", probe)
    first = health.domain_db_connectivity()
    first["AI00_FACTORY_DB_URL"] = "altered"
    assert health.domain_db_connectivity()["AI00_FACTORY_DB_URL"] == "ok"
    assert len(calls) == 1
    monkeypatch.setenv("AI00_FACTORY_DB_URL", "mysql://rotated:secret@db.example:2881/workmanship")
    assert health.domain_db_connectivity()["AI00_FACTORY_DB_URL"] == "ok"
    assert len(calls) == 2
    clock[0] += 16
    health.domain_db_connectivity()
    assert len(calls) == 3
    monkeypatch.setenv("AI00_DEPLOY_PROFILE", "production")
    health.domain_db_connectivity()
    assert len(calls) == 4


def test_ready_rejects_incomplete_domain_probe_result(monkeypatch):
    monkeypatch.setattr(health, "domain_db_configuration", lambda: "ok")
    monkeypatch.setattr(health, "domain_db_connectivity", lambda: {"USERS_DB_URL": "ok"})
    monkeypatch.setattr(health, "memory_readiness", lambda: SimpleNamespace(ready=True))
    monkeypatch.setattr(health, "connector_signing_readiness", lambda: "ok")
    monkeypatch.setattr("backend.db.connection.get_conn", lambda: pytest.fail("unexpected database connection"))
    request = SimpleNamespace(app=SimpleNamespace(openapi=lambda: {"paths": {
        route: {} for route in ("/api/tasks", "/api/projects", "/api/bop/versions",
                             "/api/v1/plugin-marketplace/registry")
    }}))
    response = health.ready(request)
    assert response.status_code == 503
    assert "AI00_ONTOLOGY_DB_URL" in response.body.decode("utf-8")


def test_ready_reports_all_domain_connections_and_migrations_when_simulated(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "plugins/craft"))
    from craft_backend.data import connection as craft_connection

    events = []

    @contextmanager
    def base_connection():
        events.append("base")
        yield object()

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql): events.append(sql)

    @contextmanager
    def craft_connection_factory():
        events.append("craft")
        yield SimpleNamespace(cursor=lambda: Cursor())

    monkeypatch.setattr(health, "memory_readiness", lambda: SimpleNamespace(ready=True))
    monkeypatch.setattr(health, "connector_signing_readiness", lambda: "ok")
    monkeypatch.setattr(health, "domain_db_configuration", lambda: "ok")
    monkeypatch.setattr(health, "domain_db_connectivity", lambda: {
        variable: "ok" for variable in REQUIRED_DB_URLS
    })
    monkeypatch.setattr("backend.db.connection.get_conn", base_connection)
    monkeypatch.setattr("backend.db.migration_readiness.assert_migrations_applied",
                        lambda conn: events.append("migrations"))
    monkeypatch.setattr(craft_connection, "get_craft_conn", craft_connection_factory)
    request = SimpleNamespace(app=SimpleNamespace(openapi=lambda: {"paths": {
        route: {} for route in ("/api/tasks", "/api/projects", "/api/bop/versions",
                             "/api/v1/plugin-marketplace/registry")
    }}))
    response = health.ready(request)
    assert response.status_code == 200
    assert json.loads(response.body)["checks"]["domain_db_connectivity"] == "ok"
    assert events == ["base", "migrations", "craft", "SELECT 1"]


def test_runtime_diagnostics_requires_super_admin():
    from backend.routers.runtime_diagnostics import require_runtime_admin

    with pytest.raises(HTTPException) as denied:
        require_runtime_admin({"system_role": "engineer", "org_role": "member"})
    assert denied.value.status_code == 403
    assert require_runtime_admin({"system_role": "super_admin"})["system_role"] == "super_admin"


def test_runtime_diagnostics_is_aggregate_and_payload_free(monkeypatch):
    from backend.routers import runtime_diagnostics

    metric = CapabilityMetricRecord(
        capability_id="craft.bop.work_package.get",
        major_version=2,
        owner_domain="craft",
        consumer_type="web",
        consumer_key_hash="sha256:abc",
        elapsed_ms=12.5,
        output_bytes=2048,
        rss_before_bytes=100,
        rss_after_bytes=120,
        cgroup_ratio=0.5,
        in_flight=1,
        cancelled=False,
        error_code=None,
    )
    gateway = SimpleNamespace(recent_metrics=lambda: (metric,))
    monkeypatch.setattr(runtime_diagnostics, "get_default_gateway", lambda: gateway)
    monkeypatch.setattr(runtime_diagnostics, "MemoryPressureSampler", lambda: _Sampler(0.5))
    monkeypatch.setenv("AI00_WEB_WORKERS", "1")

    payload = runtime_diagnostics.runtime_diagnostics({"system_role": "super_admin"})
    text = str(payload).lower()
    assert payload["worker_count"] == 1
    assert payload["memory"]["level"] == "reject_large"
    assert payload["capabilities"][0]["capability_id"] == "craft.bop.work_package.get"
    for forbidden in ("payload", "password", "database_url", "jwt", "entry_name"):
        assert forbidden not in text
