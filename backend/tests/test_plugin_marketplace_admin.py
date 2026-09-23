from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from backend.base import desktop_actions
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.tests.test_plugin_marketplace_search import marketplace
from backend.tests.test_marketplace_lifecycle_sql import lifecycle


def test_legacy_platform_routes_reject_team_admin_and_require_digest():
    from fastapi import HTTPException
    from pydantic import ValidationError
    from backend.routers import plugin_marketplace as routes
    for role in ('member', 'team_admin'):
        with pytest.raises(HTTPException) as error:
            routes._platform_admin({'is_active': True, 'system_role': role, 'org_role': role})
        assert error.value.status_code == 403
    assert routes._platform_admin({'is_active': True, 'system_role': 'super_admin'})
    for endpoint in (routes.create_publisher, routes.create_release, routes.releases, routes.review, routes.revoke):
        import inspect
        assert inspect.signature(endpoint).parameters['user'].default.dependency is routes._platform_admin
    with pytest.raises(ValidationError):
        routes.ReviewRequest(approved=True, note='Missing digest')


def test_admin_boundary_rechecks_role_before_owner_write(monkeypatch):
    from backend.base.plugin_marketplace_admin import execute, CONTRACTS
    calls = []
    monkeypatch.setattr(desktop_actions, '_actor', lambda _: {'system_role': 'team_admin'})
    monkeypatch.setattr('backend.plugin_platform.service.review_release', lambda *a, **kw: calls.append(a))
    for action in ('search', 'review', 'revoke', 'publisher', 'submit'):
        with pytest.raises(CapabilityBusinessError, match='super administrator'):
            execute(action, {}, SimpleNamespace(user_gid='u'))
    assert calls == []
    assert execute('access', {}, None) == {'can_admin': False}
    monkeypatch.setattr(desktop_actions, '_actor', lambda _: {'system_role': 'super_admin'})
    assert execute('access', {}, None) == {'can_admin': True}
    for _, _, schema, _ in CONTRACTS.values():
        assert schema['additionalProperties'] is False


def test_admin_search_is_bounded_and_does_not_expose_signatures(marketplace, monkeypatch):
    from backend.base.plugin_marketplace_admin import execute, CONTRACTS
    _, context, db = marketplace
    monkeypatch.setattr(desktop_actions, '_actor', lambda _: {'system_role': 'super_admin'})
    for column in ('publisher_id', 'review_note', 'reviewed_by', 'submitted_by'):
        db.execute(f'ALTER TABLE workmanship_plugin_releases ADD COLUMN {column} TEXT')
    result = execute('search', {'status': 'submitted', 'limit': 1}, context)
    assert [row['plugin_id'] for row in result['items']] == ['acme.pending']
    assert 'platform_signature' not in result['items'][0]
    Draft202012Validator(CONTRACTS['search'][3]).validate(result)
    with pytest.raises(CapabilityBusinessError, match='contract'):
        execute('search', {'limit': 201}, context)


def test_admin_review_binds_exact_version_digest_and_actor(monkeypatch):
    from backend.base.plugin_marketplace_admin import execute
    monkeypatch.setattr(desktop_actions, '_actor', lambda _: {'system_role': 'super_admin'})
    calls = []
    def review(*args, **kwargs):
        calls.append((args, kwargs))
        return {'plugin_id': args[0], 'version': args[1], 'status': 'rejected'}
    monkeypatch.setattr('backend.plugin_platform.service.review_release', review)
    payload = dict(plugin_id='acme.demo', version='1.0.0', release_sha256='sha256:' + 'a' * 64, approved=False, note='Missing documentation')
    assert execute('review', payload, SimpleNamespace(user_gid='trusted-user'))['status'] == 'rejected'
    assert calls[0][0][-1] == 'trusted-user'
    assert calls[0][1]['expected_sha256'] == payload['release_sha256']
    with pytest.raises(CapabilityBusinessError):
        execute('review', {**payload, 'actor_gid': 'forged'}, SimpleNamespace(user_gid='u'))


def test_admin_owner_signing_revocation_and_publisher_registration(lifecycle, monkeypatch):
    import json
    from backend.base.plugin_marketplace_admin import execute
    from backend.tests.test_plugin_lifecycle_security import Repository
    from backend.plugin_platform.signing import canonical_release, verify
    db, context, _ = lifecycle
    monkeypatch.setattr(desktop_actions, '_actor', lambda _: {'system_role': 'super_admin'})
    for field in ('review_note', 'reviewed_by', 'updated_at'):
        db.execute(f'ALTER TABLE workmanship_plugin_releases ADD COLUMN {field} TEXT')
    db.execute('ALTER TABLE workmanship_plugin_installations ADD COLUMN last_error TEXT')
    db.execute('CREATE TABLE workmanship_plugin_publishers (publisher_id TEXT,display_name TEXT,public_key_pem TEXT,key_fingerprint TEXT,created_by TEXT)')
    signing = Repository()
    publisher = {'publisher_id': 'devteam', 'display_name': 'Dev Team', 'public_key_pem': signing.platform_public_key}
    assert execute('publisher', publisher, context)['status'] == 'active'
    with pytest.raises(CapabilityBusinessError, match='already exists'):
        execute('publisher', publisher, context)
    db.execute("UPDATE workmanship_plugin_releases SET status='submitted' WHERE version='1.2.3'"); db.commit()
    target = {'plugin_id': 'devteam.example.plugin', 'version': '1.2.3', 'release_sha256': 'sha256:' + 'b' * 64, 'note': 'Verified in test'}
    monkeypatch.delenv('AI00_PLUGIN_PLATFORM_ED25519_PRIVATE_KEY', raising=False)
    with pytest.raises(CapabilityBusinessError, match='signing key'):
        execute('review', {**target, 'approved': True}, context)
    monkeypatch.setenv('AI00_PLUGIN_PLATFORM_ED25519_PRIVATE_KEY', signing._private_key)
    assert execute('review', {**target, 'approved': True}, context)['status'] == 'published'
    row = dict(db.execute("SELECT * FROM workmanship_plugin_releases WHERE version='1.2.3'").fetchone())
    verify(signing.platform_public_key, canonical_release(json.loads(row['manifest']), row['artifact_sha256']), row['platform_signature'])
    db.execute("INSERT INTO workmanship_plugin_installations (tenant_gid,plugin_id,current_version,state,mount_revocation_version,revision) VALUES ('team-b','devteam.example.plugin','1.2.3','enabled',1,2)")
    db.execute("INSERT INTO workmanship_plugin_installations (tenant_gid,plugin_id,current_version,state,mount_revocation_version,revision) VALUES ('team-c','devteam.example.plugin','2.0.0','enabled',1,2)"); db.commit()
    with pytest.raises(CapabilityBusinessError, match='digest changed'):
        execute('revoke', {**target, 'release_sha256': 'sha256:' + 'a' * 64}, context)
    assert execute('revoke', target, context)['affected_installations'] == 2
    assert [tuple(row) for row in db.execute('SELECT tenant_gid,state,revision FROM workmanship_plugin_installations ORDER BY tenant_gid')] == [('team-a', 'revoked', 5), ('team-b', 'revoked', 3), ('team-c', 'enabled', 2)]
    assert db.execute('SELECT COUNT(*) FROM workmanship_plugin_lifecycle_events').fetchone()[0] == 2


def test_gateway_admin_review_requires_confirmation_and_commits_only_matching_digest(lifecycle, monkeypatch):
    import asyncio
    from datetime import UTC, datetime
    from backend.base.plugin_marketplace_admin import register_marketplace_admin
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, InvocationEnvelope, TenantIdentity
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.capability_v2.reliability import ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter, ReliabilityCoordinator
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.routers.deps import build_capability_authorization_grants
    db, _, _ = lifecycle
    for field in ('review_note', 'reviewed_by', 'updated_at'):
        db.execute(f'ALTER TABLE workmanship_plugin_releases ADD COLUMN {field} TEXT')
    db.execute("UPDATE workmanship_plugin_releases SET status='submitted'"); db.commit()
    user = {'gid': 'admin', 'is_active': True, 'system_role': 'super_admin', 'org_role': 'super_admin', 'team_id': 'team-a'}
    monkeypatch.setattr(desktop_actions, '_actor', lambda _: user)
    monkeypatch.setattr('backend.routers.deps._get_user_grants', lambda _: [])
    registry = CapabilityRegistry(); register_marketplace_admin(registry)
    descriptor = registry.get('base.plugin.marketplace.release.review', 1).descriptor
    catalog = build_release([descriptor]); store = InMemoryCatalogStore(); store.publish(catalog)
    policy = LegacyServerGatewayPolicy(user_loader=lambda _: user,
        grants_resolver=lambda identity, actor: build_capability_authorization_grants(actor, identity.tenant.tenant_id),
        approval_service=ApprovalService(InMemoryApprovalStore()))
    gateway = CapabilityGatewayService(CatalogResolver(store, registry), policy,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100))).bind_release(catalog.release_id)
    identity = ConsumerIdentity(actor=ActorIdentity(user_id='admin', authentication_method='jwt', authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id='team-a', membership='member', active_roles=('super_admin',)),
        consumer=ConsumerDescriptor(type='web', consumer_id='ai00.desktop.windows-x64'))
    def envelope(digest, key):
        return InvocationEnvelope(capability_id=descriptor.id, major_version=1, catalog_release=catalog.release_id,
            payload={'plugin_id': 'devteam.example.plugin', 'version': '1.2.3', 'release_sha256': 'sha256:' + digest * 64, 'approved': False, 'note': 'Missing docs'},
            identity=identity, idempotency_key=key, request_id=key, trace_id=key)
    without = asyncio.run(gateway.invoke(envelope('b', 'no-confirm')))
    assert not without.ok
    for digest, key, succeeds in [('a', 'wrong-digest', False), ('b', 'matching-digest', True)]:
        request = envelope(digest, key)
        challenge = asyncio.run(gateway.request_approval(request))
        result = asyncio.run(gateway.invoke(request.model_copy(update={'approval_reference': challenge.token})))
        assert result.ok is succeeds, result.error
        if not succeeds: assert result.error.code == 'marketplace_state_conflict'
        assert db.execute("SELECT status FROM workmanship_plugin_releases WHERE version='1.2.3'").fetchone()[0] == ('rejected' if succeeds else 'submitted')
