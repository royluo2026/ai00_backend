"""Offline consumer contract and real SQL checks for the marketplace projection."""
import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from backend.base.official_provider import register_capabilities
from backend.capabilities.registry_next import CapabilityRegistry


@pytest.fixture
def marketplace(monkeypatch):
    # Import modules with module-level connection references before replacing
    # the SQL boundary, so this fixture cannot leak a closed DB into other tests.
    from backend.services import user_service
    from backend.platform_sdk import project_access
    from backend.routers import deps
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE workmanship_plugin_releases (
          plugin_id TEXT, version TEXT, manifest TEXT, artifact_sha256 TEXT,
          status TEXT, platform_signature TEXT, updated_at TEXT);
        CREATE TABLE workmanship_plugin_installations (
          tenant_gid TEXT, plugin_id TEXT, current_version TEXT, previous_version TEXT,
          state TEXT, granted_capabilities TEXT, revision INTEGER, last_error TEXT, updated_at TEXT);
        CREATE TABLE workmanship_auth_project_members (user_gid TEXT, project_gid TEXT);
    """)
    manifest = json.dumps({"name": "Demo", "description": "Demo plugin", "permissions": ["system.echo"]})
    db.executemany("INSERT INTO workmanship_plugin_releases VALUES (?,?,?,?,?,?,?)", [
        ("acme.demo", "1.0.0", manifest, "a" * 64, "published", "signed", "2026-09-20"),
        ("acme.demo", "2.0.0", manifest, "b" * 64, "published", "signed", "2026-09-22"),
        ("acme.pending", "1.0.0", manifest, "c" * 64, "submitted", None, "2026-09-22"),
    ])
    db.executemany("INSERT INTO workmanship_plugin_installations VALUES (?,?,?,?,?,?,?,?,?)", [
        ("team-a", "acme.demo", "1.0.0", None, "disabled", '["system.echo"]', 3, None, "2026-09-21"),
        ("team-b", "acme.private", "1.0.0", None, "enabled", '[]', 1, None, "2026-09-21"),
    ])

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=()): self.cursor = db.execute(sql.replace("%s", "?"), params)
        def fetchall(self): return [dict(row) for row in self.cursor.fetchall()]

    class Connection:
        def cursor(self): return Cursor()

    @contextmanager
    def connection(): yield Connection()

    monkeypatch.setattr("backend.db.connection.get_conn", connection)
    monkeypatch.setattr("backend.services.user_service.get_by_gid", lambda gid: {
        "gid": gid, "team_id": "team-a", "is_active": True, "system_role": "member", "org_role": "member",
    } if gid == "user-a" else None)
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    monkeypatch.setattr(project_access, "list_user_project_memberships", lambda _gid: [])
    registry = CapabilityRegistry()
    register_capabilities(registry)
    item = registry.get("base.plugin.marketplace.search", 2)
    yield item, SimpleNamespace(user_gid="user-a", team_gid="team-a"), db
    db.close()


def test_marketplace_search_is_versioned_closed_and_bounded(marketplace):
    item, context, _ = marketplace
    assert item.descriptor.major_version == 2
    assert item.descriptor.side_effect_level.value == "read"
    assert item.descriptor.authorization_policy == "base.v2:authenticated"
    assert item.descriptor.exposure.web is True
    schema = Draft202012Validator(dict(item.spec.input_schema))
    for invalid in ({"view": "catalog", "tenant_gid": "team-b"}, {"view": "catalog", "limit": 201}, {"view": "unknown"}):
        assert list(schema.iter_errors(invalid))
    result = item.handler({"view": "catalog", "limit": 1}, context)
    Draft202012Validator(dict(item.spec.output_schema)).validate(result)
    assert result["next_offset"] == 1
    assert result["items"][0]["version"] == "2.0.0"
    assert result["items"][0]["revision"] == 3
    assert result["items"][0]["state"] == "disabled"
    assert result["items"][0]["release_sha256"] == "sha256:" + "b" * 64
    assert "platform_signature" not in result["items"][0]


def test_installed_search_keeps_failed_rows_and_is_tenant_scoped(marketplace):
    item, context, db = marketplace
    db.execute("UPDATE workmanship_plugin_installations SET state='failed', previous_version='0.9.0' WHERE tenant_gid='team-a'")
    result = item.handler({"view": "installed"}, context)
    assert [row["plugin_id"] for row in result["items"]] == ["acme.demo"]
    assert result["items"][0]["state"] == "failed"
    assert result["items"][0]["previous_version"] == "0.9.0"
    assert result["next_offset"] is None
    assert item.handler({"view": "catalog", "query": "does-not-exist"}, context)["items"] == []
    assert item.handler({"view": "catalog", "query": "' OR 1=1 --"}, context)["items"] == []


def test_catalog_omits_unpublished_and_uninstalled_is_available(marketplace):
    item, context, db = marketplace
    db.execute("UPDATE workmanship_plugin_installations SET state='uninstalled' WHERE tenant_gid='team-a'")
    result = item.handler({"view": "catalog"}, context)
    assert len(result["items"]) == 2
    assert all(row["state"] == "available" for row in result["items"])
    assert item.handler({"view": "installed"}, context)["items"] == []


def test_malformed_stored_metadata_is_not_exposed_as_a_success(marketplace):
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    item, context, db = marketplace
    db.execute("UPDATE workmanship_plugin_releases SET manifest='invalid json'")
    with pytest.raises(CapabilityBusinessError, match="metadata"):
        item.handler({"view": "catalog"}, context)


def test_gateway_enforces_actor_tenant_version_and_closed_contract(marketplace):
    import asyncio
    from datetime import UTC, datetime
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, InvocationEnvelope, TenantIdentity
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.routers.deps import build_capability_authorization_grants
    from backend.services.user_service import get_by_gid

    item, _, _ = marketplace
    registry = CapabilityRegistry()
    register_capabilities(registry)
    release = build_release([item.descriptor])
    store = InMemoryCatalogStore(); store.publish(release)
    policy = LegacyServerGatewayPolicy(user_loader=get_by_gid,
        grants_resolver=lambda identity, user: build_capability_authorization_grants(user, identity.tenant.tenant_id))
    gateway = CapabilityGatewayService(CatalogResolver(store, registry), policy).bind_release(release.release_id)

    def invoke(payload=None, actor="user-a", tenant="team-a", major=2, consumer="web"):
        identity = ConsumerIdentity(actor=ActorIdentity(user_id=actor, authentication_method="jwt", authenticated_at=datetime.now(UTC)),
            tenant=TenantIdentity(tenant_id=tenant, membership="member", active_roles=("member",)),
            consumer=ConsumerDescriptor(type=consumer, consumer_id="ai00.web"))
        return asyncio.run(gateway.invoke(InvocationEnvelope(capability_id=item.spec.id, major_version=major,
            catalog_release=release.release_id, payload=payload or {"view": "installed"}, identity=identity,
            request_id="market-read", trace_id="market-read")))

    result = invoke()
    assert result.ok, result.error
    assert [row["plugin_id"] for row in result.data["items"]] == ["acme.demo"]
    assert not invoke(actor="missing").ok
    assert not invoke(tenant="team-b").ok
    assert not invoke(payload={"view": "installed", "tenant_gid": "team-b"}).ok
    assert not invoke(major=1).ok
    assert not invoke(consumer="agent").ok
