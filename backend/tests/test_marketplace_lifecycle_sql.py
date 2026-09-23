"""Real lifecycle SQL and signature checks against isolated in-memory storage."""
import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.plugin_platform import service
from backend.tests.test_plugin_lifecycle_security import Repository


@pytest.fixture
def lifecycle(monkeypatch):
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE workmanship_plugin_releases (plugin_id TEXT,version TEXT,manifest TEXT,artifact_sha256 TEXT,status TEXT,platform_signature TEXT);
      CREATE TABLE workmanship_plugin_installations (tenant_gid TEXT,plugin_id TEXT,current_version TEXT,previous_version TEXT,state TEXT,
        granted_capabilities TEXT,previous_granted_capabilities TEXT,mount_revocation_version INTEGER,revision INTEGER,installed_by TEXT,installation_id TEXT,updated_at TEXT);
      CREATE TABLE workmanship_plugin_lifecycle_events (gid TEXT,tenant_gid TEXT,plugin_id TEXT,from_state TEXT,to_state TEXT,version TEXT,actor_gid TEXT,detail TEXT);
    """)
    signed = Repository()
    signed.manifest["compatibility"] = {"platform_api": ">=1.0.0", "web_sdk": ">=1.0.0"}
    monkeypatch.setenv("AI00_PLUGIN_PLATFORM_ED25519_PUBLIC_KEY", signed.platform_public_key)
    monkeypatch.setenv("AI00_WEB_PLUGIN_SDK_VERSION", "1.0.0")
    monkeypatch.setattr(service.ActiveCatalogReleasePort, "resolve", lambda *_: None)
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.provider_contracts import CapabilitySpec
    registry = CapabilityRegistry()
    for capability in ("project.read", "system.echo"):
        registry.register(CapabilitySpec(id=capability, owner="base", plugin_callable=True), lambda *_: {})
    monkeypatch.setattr("backend.capability_v2.bootstrap.get_capability_registry", lambda: registry)

    def release(version, grants=None, dependency=False, tampered=False):
        signed.manifest["version"] = version
        signed.manifest["permissions"] = grants or ["project.read"]
        signed.manifest["capabilities"]["required"] = [{"id": "missing.capability", "major": 1}] if dependency else []
        signed.resign()
        db.execute("DELETE FROM workmanship_plugin_releases WHERE version=?", (version,))
        db.execute("INSERT INTO workmanship_plugin_releases VALUES (?,?,?,?,?,?)", (
            "devteam.example.plugin", version, json.dumps(signed.manifest), "b" * 64, "published",
            "invalid-signature" if tampered else signed.release_row["platform_signature"],
        ))
    release("1.2.3"); release("2.0.0", ["project.read", "system.echo"])
    db.execute("INSERT INTO workmanship_plugin_installations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
        "team-a", "devteam.example.plugin", "1.2.3", None, "disabled", '["project.read"]', None, 1, 4, "user-a", "installation-a", "today"))
    db.commit()

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=()):
            self.cursor = db.execute(sql.replace("%s", "?").replace(" FOR UPDATE", "").replace("NOW()", "CURRENT_TIMESTAMP"), params)
        def fetchone(self):
            row = self.cursor.fetchone()
            return dict(row) if row else None
        def fetchall(self): return [dict(row) for row in self.cursor.fetchall()]

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): db.commit()
        def rollback(self): db.rollback()

    @contextmanager
    def connection():
        try: yield Connection()
        except Exception:
            db.rollback()
            raise

    monkeypatch.setattr("backend.db.connection.get_conn", connection)
    yield db, SimpleNamespace(user_gid="user-a", team_gid="team-a"), release
    db.close()


def test_lifecycle_advances_revision_and_rollback_restores_grants(lifecycle):
    db, context, _ = lifecycle
    payload = {"plugin_id": "devteam.example.plugin"}
    service.transition(payload, context, "enabled")
    assert db.execute("SELECT revision FROM workmanship_plugin_installations").fetchone()[0] == 5
    service.upgrade({**payload, "version": "2.0.0", "granted_capabilities": ["project.read", "system.echo"]}, context)
    row = dict(db.execute("SELECT * FROM workmanship_plugin_installations").fetchone())
    assert (row["state"], row["revision"]) == ("upgrading", 6)
    service.rollback(payload, context)
    row = dict(db.execute("SELECT * FROM workmanship_plugin_installations").fetchone())
    assert (row["state"], row["revision"], row["current_version"]) == ("rolled_back", 7, "1.2.3")
    assert json.loads(row["granted_capabilities"]) == ["project.read"]
    assert json.loads(row["previous_granted_capabilities"]) == ["project.read", "system.echo"]


@pytest.mark.parametrize("invalid", ["signature", "dependency"])
def test_upgrade_rejects_unverified_release_without_changing_installation(lifecycle, invalid):
    db, context, release = lifecycle
    release("2.0.0", dependency=invalid == "dependency", tampered=invalid == "signature")
    db.commit()
    with pytest.raises(service.PluginLifecycleError, match="release_not_verified"):
        service.upgrade({"plugin_id": "devteam.example.plugin", "version": "2.0.0", "granted_capabilities": ["project.read"]}, context)
    row = db.execute("SELECT current_version,state,revision FROM workmanship_plugin_installations").fetchone()
    assert tuple(row) == ("1.2.3", "disabled", 4)


def test_enable_and_rollback_recheck_the_signed_release(lifecycle):
    db, context, release = lifecycle
    release("1.2.3", tampered=True); db.commit()
    with pytest.raises(service.PluginLifecycleError, match="release_not_verified"):
        service.transition({"plugin_id": "devteam.example.plugin"}, context, "enabled")
    db.execute("UPDATE workmanship_plugin_installations SET state='upgrading',previous_version='1.2.3',current_version='2.0.0',previous_granted_capabilities='[\"project.read\"]'")
    db.commit()
    with pytest.raises(service.PluginLifecycleError, match="release_not_verified"):
        service.rollback({"plugin_id": "devteam.example.plugin"}, context)
    assert db.execute("SELECT state FROM workmanship_plugin_installations").fetchone()[0] == "upgrading"


def test_gateway_reports_declared_plugin_state_conflict_for_unverified_release(lifecycle, monkeypatch):
    import asyncio
    from datetime import UTC, datetime
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capabilities.plugin_marketplace_next import register_plugin_marketplace_capabilities
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, InvocationEnvelope, TenantIdentity
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.capability_v2.reliability import ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter, ReliabilityCoordinator
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.routers.deps import build_capability_authorization_grants

    db, _, release = lifecycle
    release("1.2.3", tampered=True); db.commit()
    monkeypatch.setattr("backend.routers.deps._get_user_grants", lambda _: [])
    registry = CapabilityRegistry(); register_plugin_marketplace_capabilities(registry)
    descriptor = registry.get("plugin.enable", 1).descriptor
    catalog = build_release([descriptor]); store = InMemoryCatalogStore(); store.publish(catalog)
    user = {"gid": "admin", "is_active": True, "system_role": "super_admin", "org_role": "super_admin", "team_id": "team-a"}
    policy = LegacyServerGatewayPolicy(user_loader=lambda _: user,
        grants_resolver=lambda identity, actor: build_capability_authorization_grants(actor, identity.tenant.tenant_id),
        approval_service=ApprovalService(InMemoryApprovalStore()))
    gateway = CapabilityGatewayService(CatalogResolver(store, registry), policy,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100))).bind_release(catalog.release_id)
    identity = ConsumerIdentity(actor=ActorIdentity(user_id="admin", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-a", membership="member", active_roles=("super_admin",)),
        consumer=ConsumerDescriptor(type="web", consumer_id="ai00.desktop.windows-x64"))
    envelope = InvocationEnvelope(capability_id="plugin.enable", major_version=1, catalog_release=catalog.release_id,
        payload={"plugin_id": "devteam.example.plugin"}, identity=identity, idempotency_key="enable-invalid",
        request_id="enable-invalid", trace_id="enable-invalid")
    challenge = asyncio.run(gateway.request_approval(envelope))
    result = asyncio.run(gateway.invoke(envelope.model_copy(update={"approval_reference": challenge.token})))
    assert result.error.code == "plugin_state_conflict"
    assert result.error.code in {error.code for error in descriptor.domain_errors}
    assert db.execute("SELECT state,revision FROM workmanship_plugin_installations").fetchone()[:] == ("disabled", 4)
