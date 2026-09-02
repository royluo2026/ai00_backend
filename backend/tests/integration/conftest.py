"""Shared fixtures for Capability V2 integration tests.

Static fixtures (no DB) work in the default offline mode.
DB-backed fixtures are auto-skipped unless AI00_ALLOW_LIVE_DB_TESTS=1.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generator
from types import SimpleNamespace

import pytest

from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    CorrelationRef,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService, configure_default_gateway

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = Path("E:/Projects/ai00/workmanship-web").resolve()

# ---------------------------------------------------------------------------
# pytest markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring a real database connection",
    )


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _skip_if_no_live_db():
    if os.environ.get("AI00_ALLOW_LIVE_DB_TESTS") != "1":
        pytest.skip("Requires AI00_ALLOW_LIVE_DB_TESTS=1 for live DB tests")


def _skip_if_no_env(var: str):
    if not os.environ.get(var):
        pytest.skip(f"Requires {var} for this integration test")


# ---------------------------------------------------------------------------
# Session-level: Registry and Gateway
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def integration_factory_env():
    """Ensure AI00_INTEGRATION_ADAPTER_FACTORY is set for the session.

    Uses the test adapter stub declared in plugins/integration/tests/
    if not already configured.
    """
    if not os.environ.get("AI00_INTEGRATION_ADAPTER_FACTORY"):
        os.environ["AI00_INTEGRATION_ADAPTER_FACTORY"] = (
            "integration_test_adapter_factory:build"
        )
    yield
    # Leave the env var in place — tests may rely on it for the session.


@pytest.fixture(scope="session")
def registry(integration_factory_env):
    """Load the complete official 11-domain Capability Registry once per session."""
    return build_capability_registry(REPO_ROOT)


@pytest.fixture(scope="session")
def gateway(registry) -> CapabilityGatewayService:
    """Configure the default Gateway against the session registry."""
    return configure_default_gateway(registry)


# ---------------------------------------------------------------------------
# Identity fixtures
# ---------------------------------------------------------------------------

def _make_identity(
    consumer_type: ConsumerType,
    *,
    user_id: str = "user_int_test_1",
    tenant_id: str = "tenant_int_test_1",
    active_roles: tuple[str, ...] = ("member",),
) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id=user_id,
            authentication_method="jwt",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(
            tenant_id=tenant_id,
            membership="member",
            active_roles=active_roles,
        ),
        consumer=ConsumerDescriptor(
            type=consumer_type,
            consumer_id=f"integration-test.{consumer_type.value}",
        ),
    )


@pytest.fixture
def web_identity() -> ConsumerIdentity:
    """Standard WEB consumer identity for integration tests."""
    return _make_identity(ConsumerType.WEB)


@pytest.fixture
def agent_identity() -> ConsumerIdentity:
    """Standard AGENT consumer identity."""
    return _make_identity(ConsumerType.AGENT)


@pytest.fixture
def service_identity() -> ConsumerIdentity:
    """Service-to-service identity used in cross-domain tests."""
    return _make_identity(ConsumerType.API)


# ---------------------------------------------------------------------------
# Invocation envelope helper
# ---------------------------------------------------------------------------

def make_envelope(
    gateway: CapabilityGatewayService,
    capability_id: str,
    payload: dict[str, Any],
    identity: ConsumerIdentity,
    *,
    major_version: int = 1,
    idempotency_key: str | None = None,
    request_id: str = "req_int_test",
    trace_id: str = "trace_int_test",
) -> InvocationEnvelope:
    """Construct an InvocationEnvelope ready to be sent to the Gateway."""
    return InvocationEnvelope(
        capability_id=capability_id,
        major_version=major_version,
        catalog_release=gateway.catalog_release,
        payload=payload,
        identity=identity,
        idempotency_key=idempotency_key,
        request_id=request_id,
        trace_id=trace_id,
    )


def invoke_sync(
    gateway: CapabilityGatewayService,
    capability_id: str,
    payload: dict[str, Any],
    identity: ConsumerIdentity,
    **kwargs: Any,
):
    """Run an async Gateway.invoke() call synchronously in tests."""
    envelope = make_envelope(gateway, capability_id, payload, identity, **kwargs)
    return asyncio.run(gateway.invoke(envelope))


# ---------------------------------------------------------------------------
# Database connection fixtures (skip unless AI00_ALLOW_LIVE_DB_TESTS=1)
# ---------------------------------------------------------------------------

@contextmanager
def _pymysql_connection(url: str, *, cursor_class=None):
    """Yield a raw PyMySQL connection from a URL string."""
    pymysql = pytest.importorskip("pymysql")
    from urllib.parse import urlparse
    parsed = urlparse(url)
    kwargs = dict(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password or "",
        database=(parsed.path or "").lstrip("/"),
        charset="utf8mb4",
        cursorclass=cursor_class or pymysql.cursors.DictCursor,
        autocommit=False,
    )
    conn = pymysql.connect(**kwargs)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _db_factory(env_var: str):
    """Return a context-manager factory for one domain's database, or skip."""
    _skip_if_no_live_db()
    url = os.environ.get(env_var, "")
    if not url:
        pytest.skip(f"{env_var} is not configured")

    @contextmanager
    def factory():
        with _pymysql_connection(url) as conn:
            yield conn

    return factory


@pytest.fixture
def craft_db():
    """Factory: context manager yielding a Craft-domain DB connection."""
    return _db_factory("AI00_CRAFT_DB_URL")


@pytest.fixture
def knowledge_db():
    """Factory: context manager yielding a Knowledge-domain DB connection."""
    return _db_factory("AI00_KNOWLEDGE_DB_URL")


@pytest.fixture
def project_db():
    """Factory: context manager yielding a Project-Management-domain DB connection."""
    return _db_factory("AI00_PROJECT_MANAGEMENT_DB_URL")


@pytest.fixture
def base_db():
    """Factory: context manager yielding a Base-Platform DB connection."""
    return _db_factory("AI00_BASE_DB_URL")


@pytest.fixture
def factory_db():
    """Factory: context manager yielding a Factory-domain DB connection."""
    return _db_factory("AI00_FACTORY_DB_URL")
