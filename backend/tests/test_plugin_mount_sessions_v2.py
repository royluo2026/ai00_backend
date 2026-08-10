from __future__ import annotations

from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
import asyncio
from pathlib import Path

import pytest

from backend.plugin_platform.manifest import parse_manifest
from backend.plugin_platform.mounts import (
    InMemoryMountSessionStore,
    MountSessionError,
    MountSessionService,
    SqlMountSessionStore,
)
from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus, CorrelationRef
from backend.capability_v2.identity import AuthenticatedPrincipal


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _manifest():
    return {
        "schema_version": "2.0",
        "plugin_id": "acme.ai00.example",
        "publisher_id": "acme",
        "name": "Example",
        "version": "1.0.0",
        "compatibility": {"platform_api": ">=2.0.0 <3.0.0", "web_sdk": "^0.2.0"},
        "runtimes": {"web": {"entry": "index.html", "sandbox": "allow-scripts"}},
        "permissions": [],
        "capabilities": {
            "required": [],
            "optional": [{"id": "craft.routing.get", "major": 1}],
        },
        "artifact": {
            "object_key": "plugins/acme/acme.ai00.example/1.0.0/" + "a" * 64 + ".zip",
            "sha256": "a" * 64,
            "size": 100,
            "media_type": "application/zip",
        },
        "data": {"stores_personal_data": False, "retention": "none", "uninstall": "delete"},
    }


def test_optional_capability_does_not_block_manifest_parse():
    manifest = parse_manifest(_manifest())
    assert manifest.capabilities.required == ()
    assert manifest.capabilities.optional[0].id == "craft.routing.get"
    assert manifest.capabilities.optional[0].major == 1


def test_mount_session_binds_user_installation_release_scopes_and_token_hash(monkeypatch):
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "test-secret-value-with-at-least-thirty-two-bytes")
    store = InMemoryMountSessionStore(clock=lambda: NOW)
    service = MountSessionService(store, clock=lambda: NOW)
    issued = service.issue(
        user_id="user-1", tenant_id="tenant-1", installation_id="install-1",
        plugin_id="acme.ai00.example", plugin_version="1.0.0",
        artifact_sha256="a" * 64, catalog_release="rel_" + "b" * 32,
        capability_grants=("craft.routing.get@1",),
        resource_scopes=("project:p1",), data_scopes=("internal",),
        revocation_version=3, authenticated_at=NOW,
    )

    session = service.resolve_for_user(
        issued.session.mount_session_id, current_user_id="user-1", current_tenant_id="tenant-1"
    )
    assert session.installation_id == "install-1"
    assert session.catalog_release == "rel_" + "b" * 32
    assert session.capability_grants == ("craft.routing.get@1",)
    assert issued.asset_token not in repr(store.snapshot())
    assert issued.asset_token_hash in repr(store.snapshot())


def test_mount_session_and_asset_token_cannot_cross_users_or_routes(monkeypatch):
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "test-secret-value-with-at-least-thirty-two-bytes")
    store = InMemoryMountSessionStore(clock=lambda: NOW)
    service = MountSessionService(store, clock=lambda: NOW)
    issued = service.issue(
        user_id="user-1", tenant_id="tenant-1", installation_id="install-1",
        plugin_id="acme.ai00.example", plugin_version="1.0.0",
        artifact_sha256="a" * 64, catalog_release="rel_" + "b" * 32,
        capability_grants=(), resource_scopes=(), data_scopes=("internal",),
        revocation_version=1, authenticated_at=NOW,
    )
    with pytest.raises(MountSessionError, match="user"):
        service.resolve_for_user(
            issued.session.mount_session_id, current_user_id="user-2", current_tenant_id="tenant-1"
        )
    claims = service.resolve_asset_token(issued.asset_token)
    assert claims.mount_session_id == issued.session.mount_session_id
    with pytest.raises(MountSessionError, match="route"):
        service.resolve_asset_token(
            issued.asset_token, expected_plugin_id="acme.ai00.other", expected_version="1.0.0"
        )


def test_mount_revocation_and_expiry_fail_closed(monkeypatch):
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "test-secret-value-with-at-least-thirty-two-bytes")
    now = [NOW]
    store = InMemoryMountSessionStore(clock=lambda: now[0])
    service = MountSessionService(store, clock=lambda: now[0])
    issued = service.issue(
        user_id="user-1", tenant_id="tenant-1", installation_id="install-1",
        plugin_id="acme.ai00.example", plugin_version="1.0.0",
        artifact_sha256="a" * 64, catalog_release="rel_" + "b" * 32,
        capability_grants=(), resource_scopes=(), data_scopes=(), revocation_version=1,
        authenticated_at=NOW, ttl=timedelta(minutes=5),
    )
    store.revoke_installation("install-1", new_revocation_version=2)
    with pytest.raises(MountSessionError, match="revoked"):
        service.resolve_for_user(
            issued.session.mount_session_id, current_user_id="user-1", current_tenant_id="tenant-1"
        )

    second = service.issue(
        user_id="user-1", tenant_id="tenant-1", installation_id="install-2",
        plugin_id="acme.ai00.example", plugin_version="1.0.0",
        artifact_sha256="a" * 64, catalog_release="rel_" + "b" * 32,
        capability_grants=(), resource_scopes=(), data_scopes=(), revocation_version=1,
        authenticated_at=NOW, ttl=timedelta(minutes=5),
    )
    now[0] += timedelta(minutes=6)
    with pytest.raises(MountSessionError, match="expired"):
        service.resolve_asset_token(second.asset_token)


def test_mount_migration_and_host_bridge_preserve_full_result():
    root = Path(__file__).resolve().parents[2]
    sql = (root / "backend/db/migrations/202608100005_base_plugin_mount_sessions.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "workmanship_plugin_mount_sessions" in sql
    assert "asset_token_hash" in sql and "asset_token" not in sql.replace("asset_token_hash", "")
    assert "catalog_release" in sql and "revocation_version" in sql
    assert "installation_id" in sql

    host = (root / "packages/plugin-sdk/src/host.ts").read_text(encoding="utf-8")
    assert "result: data" not in host
    assert "result" in host
    assert "success: true, data" not in host


def test_sql_mount_store_persists_only_asset_token_hash(monkeypatch):
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "test-secret-value-with-at-least-thirty-two-bytes")

    class Cursor:
        rowcount = 1
        statements = []
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params=()): self.statements.append((" ".join(sql.split()), params))

    class Connection:
        def cursor(self): return cursor

    cursor = Cursor()
    @contextmanager
    def connections():
        yield Connection()

    service = MountSessionService(SqlMountSessionStore(connections), clock=lambda: NOW)
    issued = service.issue(
        user_id="user-1", tenant_id="tenant-1", installation_id="install-1",
        plugin_id="acme.ai00.example", plugin_version="1.0.0",
        artifact_sha256="a" * 64, catalog_release="rel_" + "b" * 32,
        capability_grants=(), resource_scopes=(), data_scopes=(),
        revocation_version=1, authenticated_at=NOW,
    )
    sql, params = cursor.statements[0]
    assert "asset_token_hash" in sql
    assert issued.asset_token not in params
    assert issued.asset_token_hash in params


def test_plugin_mount_invoke_constructs_trusted_identity_and_returns_full_result(monkeypatch):
    from backend.routers import plugin_marketplace as router_module

    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "test-secret-value-with-at-least-thirty-two-bytes")
    store = InMemoryMountSessionStore(clock=lambda: NOW)
    issued = MountSessionService(store, clock=lambda: NOW).issue(
        user_id="user-1", tenant_id="tenant-1", installation_id="install-1",
        plugin_id="acme.ai00.example", plugin_version="1.0.0",
        artifact_sha256="a" * 64, catalog_release="rel_" + "b" * 32,
        capability_grants=("system.echo@1",), resource_scopes=("tenant:tenant-1",),
        data_scopes=("internal",), revocation_version=1, authenticated_at=NOW,
    )
    captured = []

    class Gateway:
        async def invoke(self, envelope):
            captured.append(envelope)
            return CapabilityResultV2(
                ok=True, status=CapabilityStatus.COMPLETED,
                capability_id=envelope.capability_id, major_version=envelope.major_version,
                data={"echo": True},
                correlation=CorrelationRef(request_id=envelope.request_id, trace_id=envelope.trace_id),
            )

    monkeypatch.setattr(router_module, "_resolve_mount_for_user", lambda *_args, **_kwargs: issued.session)
    monkeypatch.setattr(router_module, "get_default_gateway", lambda: Gateway())
    result = asyncio.run(router_module.invoke_from_mount(
        issued.session.mount_session_id, "system.echo",
        router_module.MountInvokeRequest(payload={"value": "x"}, major_version=1),
        {"gid": "user-1", "team_id": "tenant-1", "org_role": "member"},
        AuthenticatedPrincipal(
            user_id="user-1", authentication_method="jwt", authenticated_at=NOW,
        ),
    ))
    assert result["ok"] is True and result["status"] == "completed"
    assert "success" not in result
    assert captured[0].identity.consumer.mount_session_id == issued.session.mount_session_id
    assert captured[0].identity.consumer.installation_id == "install-1"
