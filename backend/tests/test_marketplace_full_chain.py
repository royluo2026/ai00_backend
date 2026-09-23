"""Controlled backend E2E: real owners/Gateway/signatures/SQL, isolated stores.

Set AI00_MARKETPLACE_E2E_BUNDLES to the prepared reference package directory.
No live account, production database, OIS or desktop GUI is impersonated.
"""
import asyncio
import hashlib
import io
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_signed_reference_package_full_backend_chain(monkeypatch, tmp_path):
    from backend.services import user_service
    from backend.routers import deps, plugin_marketplace as router
    from backend.platform_sdk import artifacts as artifact_sdk, project_access
    from backend.base.official_provider import register_capabilities
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.artifacts import ArtifactService, InMemoryArtifactStore, FilesystemObjectStorage
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, InvocationEnvelope, TenantIdentity
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.capability_v2.reliability import ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter, ReliabilityCoordinator
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.provider_contracts import CapabilitySpec
    from backend.plugin_platform import service
    from backend.plugin_platform.package_upload import unpack_bundle
    from backend.plugin_platform.mounts import MountSessionService, SqlMountSessionStore, MountSessionError
    from backend.tests.test_plugin_lifecycle_security import Repository

    package_dir = os.environ.get('AI00_MARKETPLACE_E2E_BUNDLES')
    if not package_dir:
        pytest.skip('Set AI00_MARKETPLACE_E2E_BUNDLES to signed reference packages (no live credentials required).')
    directory = Path(package_dir)
    packages = [(p, *unpack_bundle(p.read_bytes())) for p in sorted(directory.glob('*.ai00pkg'))]
    assert len(packages) == 2
    plugin_id = packages[0][1].plugin_id
    first_version, second_version = (row[1].version for row in packages)
    assert all(row[1].plugin_id == plugin_id for row in packages)
    evidence = []
    db = sqlite3.connect(tmp_path / 'marketplace.sqlite', check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE workmanship_plugin_publishers (publisher_id TEXT PRIMARY KEY,display_name TEXT,public_key_pem TEXT,key_fingerprint TEXT,created_by TEXT,status TEXT DEFAULT 'active');
      CREATE TABLE workmanship_plugin_releases (plugin_id TEXT,version TEXT,publisher_id TEXT,manifest TEXT,artifact_object_key TEXT,artifact_sha256 TEXT,publisher_signature TEXT,platform_signature TEXT,submitted_by TEXT,status TEXT DEFAULT 'submitted',review_note TEXT,reviewed_by TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(plugin_id,version));
      CREATE TABLE workmanship_plugin_installations (tenant_gid TEXT,plugin_id TEXT,current_version TEXT,previous_version TEXT,state TEXT,granted_capabilities TEXT,previous_granted_capabilities TEXT,installed_by TEXT,installation_id TEXT,mount_revocation_version INTEGER,revision INTEGER,last_error TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(tenant_gid,plugin_id));
      CREATE TABLE workmanship_base_plugin_lifecycle_idempotency (tenant_gid TEXT,actor_gid TEXT,operation TEXT,idempotency_key TEXT,command_sha256 TEXT,status TEXT,result_json TEXT,completed_at TEXT,PRIMARY KEY(tenant_gid,actor_gid,operation,idempotency_key));
      CREATE TABLE workmanship_plugin_lifecycle_events (gid TEXT,tenant_gid TEXT,plugin_id TEXT,from_state TEXT,to_state TEXT,version TEXT,actor_gid TEXT,detail TEXT);
      CREATE TABLE workmanship_plugin_namespace_kv (tenant_gid TEXT,plugin_id TEXT,value_key TEXT,value_json TEXT);
      CREATE TABLE workmanship_auth_project_members (user_gid TEXT,project_gid TEXT);
      CREATE TABLE e2e_gateway_outcomes (operation_id TEXT PRIMARY KEY,status TEXT);
      CREATE TABLE workmanship_plugin_mount_sessions (mount_session_id TEXT PRIMARY KEY,asset_token_hash TEXT,user_id TEXT,tenant_id TEXT,installation_id TEXT,plugin_id TEXT,plugin_version TEXT,artifact_sha256 TEXT,catalog_release TEXT,capability_grants_json TEXT,resource_scopes_json TEXT,data_scopes_json TEXT,revocation_version INTEGER,status TEXT,authenticated_at TEXT,created_at TEXT,expires_at TEXT,revoked_at TEXT);
    ''')

    def row(value):
        if value is None: return None
        value = dict(value)
        if 'mount_session_id' in value:
            for field in ('authenticated_at', 'created_at', 'expires_at', 'revoked_at'):
                if value.get(field): value[field] = datetime.fromisoformat(value[field])
        return value

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=()):
            sql = sql.replace('%s', '?').replace(' FOR UPDATE', '').replace(' COLLATE utf8mb4_general_ci', '')
            sql = re.sub(r'(?:UTC_TIMESTAMP|CURRENT_TIMESTAMP)\(6\)|NOW\(\)', 'CURRENT_TIMESTAMP', sql)
            if 'ON DUPLICATE KEY UPDATE' in sql:
                sql, update = sql.split('ON DUPLICATE KEY UPDATE')
                conflict = 'tenant_gid,plugin_id' if 'INSERT INTO workmanship_plugin_installations ' in sql else 'tenant_gid,actor_gid,operation,idempotency_key'
                update = re.sub(r'VALUES\((\w+)\)', r'excluded.\1', update)
                sql += f'ON CONFLICT({conflict}) DO UPDATE SET {update}'
            self.cursor = db.execute(sql, tuple(value.isoformat() if isinstance(value, datetime) else value for value in params))
            self.rowcount = self.cursor.rowcount
        def fetchone(self): return row(self.cursor.fetchone())
        def fetchall(self): return [row(value) for value in self.cursor.fetchall()]

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): db.commit()
        def rollback(self): db.rollback()

    @contextmanager
    def connection():
        try: yield Connection()
        except Exception:
            db.rollback(); raise

    monkeypatch.setattr('backend.db.connection.get_conn', connection)
    user = {'gid': 'e2e-admin', 'is_active': True, 'system_role': 'super_admin', 'org_role': 'super_admin', 'team_id': 'e2e-team'}
    monkeypatch.setattr(user_service, 'get_by_gid', lambda gid: user if gid == user['gid'] else None)
    monkeypatch.setattr(deps, '_get_user_grants', lambda _: [])
    monkeypatch.setattr(project_access, 'list_user_project_memberships', lambda _: [])
    platform = Repository()
    monkeypatch.setenv('AI00_PLUGIN_PLATFORM_ED25519_PRIVATE_KEY', platform._private_key)
    monkeypatch.setenv('AI00_PLUGIN_PLATFORM_ED25519_PUBLIC_KEY', platform.platform_public_key)
    monkeypatch.setenv('AI00_PLUGIN_MOUNT_SECRET', 'isolated-e2e-mount-secret-not-a-live-credential')
    monkeypatch.setenv('AI00_PLATFORM_API_VERSION', '1.0.0')
    monkeypatch.setenv('AI00_WEB_PLUGIN_SDK_VERSION', '0.1.0')
    registry = CapabilityRegistry(); register_capabilities(registry)
    # The reference plugin's Craft call is outside this marketplace test; only
    # its published exposure metadata is needed for the signed grant check.
    registry.register(CapabilitySpec(id='craft.bop.version.list', owner='craft', plugin_callable=True), lambda *_: {})
    monkeypatch.setattr('backend.capability_v2.bootstrap.get_capability_registry', lambda: registry)
    catalog = build_release(item.descriptor for item in registry.snapshot() if item.descriptor)
    store = InMemoryCatalogStore(); store.publish(catalog)
    policy = LegacyServerGatewayPolicy(user_loader=lambda _: user,
        grants_resolver=lambda identity, actor: deps.build_capability_authorization_grants(actor, identity.tenant.tenant_id),
        approval_service=ApprovalService(InMemoryApprovalStore()))
    class OutcomeStore(InMemoryOutcomeStore):
        fail_next = False
        def complete_in_transaction(self, transaction, operation_id, result, **kwargs):
            with transaction.cursor() as cursor:
                cursor.execute('INSERT INTO e2e_gateway_outcomes VALUES (%s,%s)', (operation_id, result.status.value))
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError('Injected outcome persistence failure')
            return self.complete(operation_id, result, **kwargs)
    outcomes = OutcomeStore()
    gateway = CapabilityGatewayService(CatalogResolver(store, registry), policy,
        reliability=ReliabilityCoordinator(outcomes, InMemoryRateLimiter(limit=1000))).bind_release(catalog.release_id)
    monkeypatch.setattr('backend.capability_v2.gateway.get_default_gateway', lambda: gateway)
    identity = ConsumerIdentity(actor=ActorIdentity(user_id=user['gid'], authentication_method='isolated-test', authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id=user['team_id'], membership='member', active_roles=('super_admin',)),
        consumer=ConsumerDescriptor(type='web', consumer_id='ai00.desktop.windows-x64'))
    serial = 0

    def invoke(cap, payload, major=1, *, write=True, expected_error=None):
        nonlocal serial
        serial += 1; key = f'e2e-{serial}'
        if cap in ('base.plugin.installation.request.create', 'base.plugin.installation.transition.uninstall'):
            payload = {**payload, 'idempotency_key': key}
        envelope = InvocationEnvelope(capability_id=cap, major_version=major, catalog_release=catalog.release_id,
            identity=identity, payload=payload, idempotency_key=key if write else None, request_id=key, trace_id=key)
        if write:
            approval = asyncio.run(gateway.request_approval(envelope))
            envelope = envelope.model_copy(update={'approval_reference': approval.token})
        result = asyncio.run(gateway.invoke(envelope))
        if expected_error:
            assert not result.ok and result.error.code == expected_error, result
            evidence.append({'step': cap, 'expected_rejection': expected_error}); return None
        assert result.ok, result.error
        evidence.append({'step': cap, 'status': result.status.value})
        return result.data

    blob_store = FilesystemObjectStorage(tmp_path / 'blobs')
    artifacts = ArtifactService(InMemoryArtifactStore(), blob_store)
    monkeypatch.setattr(artifact_sdk, 'artifact_service', lambda: artifacts)

    def immutable_put(key, data, mime):
        target = blob_store.path_for(key)
        if target.exists(): assert target.read_bytes() == data
        else: blob_store.put_stream(key, io.BytesIO(data))
        return {'object_key': key, 'sha256': hashlib.sha256(data).hexdigest()}

    monkeypatch.setattr('backend.core.storage.put_immutable', immutable_put)
    monkeypatch.setattr('backend.core.storage.get_immutable', lambda key: blob_store.path_for(key).read_bytes())
    invoke('base.plugin.marketplace.publisher.register', {'publisher_id': packages[0][1].publisher_id, 'display_name': 'Isolated E2E Publisher', 'public_key_pem': (directory / 'publisher-public.pem').read_text()}, 2)
    for path, manifest, _, _ in packages:
        data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
        upload = artifacts.create_upload(identity, media_type='application/zip', expected_sha256=digest, expected_byte_size=len(data))
        artifacts.upload_stream(upload.upload_id, identity, io.BytesIO(data))
        ref = artifacts.finalize(upload.upload_id, identity, reported_sha256=digest)
        evidence.append({'step': 'virtual_upload', 'file': path.name, 'sha256': digest})
        invoke('base.plugin.marketplace.release.submit', {'artifact_ref': ref.model_dump(mode='json')})
        invoke('base.plugin.marketplace.release.review', {'plugin_id': plugin_id, 'version': manifest.version, 'release_sha256': 'sha256:' + manifest.artifact.sha256, 'approved': True, 'note': 'Isolated backend E2E test, not governance approval'})
    grants = list(packages[0][1].permissions)
    outcomes.fail_next = True
    invoke('base.plugin.installation.request.create', {'plugin_id': plugin_id, 'release_version': first_version, 'release_sha256': 'sha256:' + packages[0][1].artifact.sha256, 'requested_grants': grants}, expected_error='outcome_persistence_failed')
    assert db.execute('SELECT COUNT(*) FROM workmanship_plugin_installations').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM e2e_gateway_outcomes').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM workmanship_base_plugin_lifecycle_idempotency').fetchone()[0] == 0
    evidence.append({'step': 'outcome_failure_rolls_back_installation_and_idempotency', 'status': 'passed'})
    install = invoke('base.plugin.installation.request.create', {'plugin_id': plugin_id, 'release_version': first_version, 'release_sha256': 'sha256:' + packages[0][1].artifact.sha256, 'requested_grants': grants})
    assert install['installation']['state'] == 'disabled'
    invoke('plugin.enable', {'plugin_id': plugin_id})
    assert service.tenant_registry(user)[0]['version'] == first_version
    mounts = MountSessionService(SqlMountSessionStore(connection))
    monkeypatch.setattr(router, '_mount_service', lambda: mounts)

    def mount(version):
        installed = dict(db.execute('SELECT * FROM workmanship_plugin_installations').fetchone())
        manifest = next(item[1] for item in packages if item[1].version == version)
        issued = mounts.issue(user_id=user['gid'], tenant_id=user['team_id'], installation_id=installed['installation_id'], plugin_id=plugin_id,
            plugin_version=version, artifact_sha256=manifest.artifact.sha256, catalog_release=catalog.release_id, capability_grants=(),
            resource_scopes=(), data_scopes=(), revocation_version=installed['mount_revocation_version'], authenticated_at=datetime.now(UTC))
        response = router.plugin_asset(issued.asset_token, plugin_id, version, 'index.html')
        assert response.status_code == 200 and b'Hello' in response.body
        assert "connect-src 'none'" in response.headers['Content-Security-Policy']
        evidence.append({'step': 'mount_asset', 'version': version, 'status': 200})
        return issued

    first_mount = mount(first_version)
    invoke('plugin.upgrade', {'plugin_id': plugin_id, 'version': second_version, 'granted_capabilities': grants})
    with pytest.raises(MountSessionError): mounts.resolve_asset_token(first_mount.asset_token)
    invoke('plugin.rollback', {'plugin_id': plugin_id})
    mount(first_version)
    invoke('plugin.upgrade', {'plugin_id': plugin_id, 'version': second_version, 'granted_capabilities': grants})
    invoke('plugin.enable', {'plugin_id': plugin_id})
    final_mount = mount(second_version)
    invoke('plugin.disable', {'plugin_id': plugin_id})
    assert service.tenant_registry(user) == []
    with pytest.raises(MountSessionError): mounts.resolve_asset_token(final_mount.asset_token)
    db.execute('INSERT INTO workmanship_plugin_namespace_kv VALUES (?,?,?,?)', (user['team_id'], plugin_id, 'keep', '"retained"')); db.commit()
    revision = db.execute('SELECT revision FROM workmanship_plugin_installations').fetchone()[0]
    invoke('base.plugin.installation.transition.uninstall', {'plugin_id': plugin_id, 'expected_revision': revision - 1, 'retain_tenant_data': True}, expected_error='revision_conflict')
    result = invoke('base.plugin.installation.transition.uninstall', {'plugin_id': plugin_id, 'expected_revision': revision, 'retain_tenant_data': True})
    assert result['installation']['state'] == 'uninstalled'
    assert db.execute('SELECT COUNT(*) FROM workmanship_plugin_namespace_kv').fetchone()[0] == 1
    assert db.execute('SELECT COUNT(*) FROM e2e_gateway_outcomes').fetchone()[0] == 2
    evidence.append({'step': 'uninstall_preserves_data_and_revokes_mounts', 'status': 'passed'})
    output = os.environ.get('AI00_MARKETPLACE_E2E_REPORT')
    if output:
        Path(output).write_text(json.dumps({'kind': 'isolated_backend_end_to_end', 'real': ['Gateway', 'ArtifactService', 'signatures', 'SQL owners', 'mount asset route'], 'test_adapters': ['SQLite dialect', 'filesystem instead of OIS', 'in-memory approval/outcome/artifact metadata', 'test identity', 'Craft exposure metadata'], 'desktop_gui': 'not_run', 'steps': evidence}, indent=2), encoding='utf-8')
    db.close()
