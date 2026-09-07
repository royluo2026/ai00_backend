from __future__ import annotations

import base64
from datetime import timedelta
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from backend.tests.test_simulation_connector_runtime_v2_sql import database, NOW, read, queue, lease
from plugins.simulation.simulation_backend.domain.connector_pairing import PairingService, PairingError
from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def keys():
    signing = ec.generate_private_key(ec.SECP256R1())
    p = signing.public_key().public_numbers()
    jwk = dict(kty='EC', crv='P-256', x=b64(p.x.to_bytes(32, 'big')), y=b64(p.y.to_bytes(32, 'big')))
    encryption = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    p = encryption.public_key().public_numbers()
    encryption_jwk = dict(kty='RSA', alg='RSA-OAEP-256', n=b64(p.n.to_bytes(256, 'big')), e=b64(p.e.to_bytes(3, 'big')))
    return signing, jwk, encryption, encryption_jwk


def sign(key, challenge):
    from backend.contracts.connector_execution_plan_v2 import P256_ORDER
    r, s = decode_dss_signature(key.sign(challenge.encode(), ec.ECDSA(hashes.SHA256())))
    return b64(r.to_bytes(32, 'big') + min(s, P256_ORDER - s).to_bytes(32, 'big'))


def setup_service(database):
    from plugins.simulation.simulation_backend.application.connector_runtime_sessions import RuntimeSessionService
    key, jwk, _, _ = keys()
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_devices SET device_signing_jwk=%s,device_credential_hash=%s WHERE device_id=%s',
                    (json.dumps(jwk), hashlib.sha256(b'device-secret').hexdigest(), database[1]))
    return RuntimeSessionService(SimulationConnectorRepository(), clock=lambda: NOW), key


def register(service, key, device, instance='winner', generation=7, plan_id=None):
    challenge = service.challenge(device, 'device-secret', generation, instance, runtime_type='electron', plan_id=plan_id)
    method = service.register_reconciliation if plan_id else service.register
    kwargs = {'plan_id': plan_id} if plan_id else {}
    return method(device, generation, instance, device_credential='device-secret', runtime_type='electron',
                  challenge=challenge['challenge'], signature=sign(key, challenge['challenge']), **kwargs)


def test_pairing_retains_signing_key_and_discards_bootstrap_key(database):
    from plugins.simulation.simulation_backend.data.connector_app_pairing_repository import SqlAppPairingRepository
    service = PairingService(SqlAppPairingRepository(), clock=lambda: NOW)
    key, jwk, encryption, encryption_jwk = keys()
    pending = service.request_v2(jwk, encryption_jwk, 'nonce-' + database[1])
    assert pending['status'] == 'created'
    service.bind_v2(pending['pairing_id'], 'user-001', 'tenant-001', expected_version=1)
    decrypted = encryption.decrypt(base64.urlsafe_b64decode(pending['encrypted_challenge'] + '=='),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)).decode()
    activated = service.activate_v2(pending['pairing_id'], pending['signing_challenge'], sign(key, pending['signing_challenge']), decrypted)
    assert activated['bootstrap_key_retained'] is False
    record = service.repository.get_pairing(pending['pairing_id'])
    assert record['status'] == 'activated'
    assert record['bootstrap_encryption_jwk'] == {}
    assert record['device_signing_jwk'] == jwk
    assert record['signing_challenge_hash'] is None
    assert 'device_credential' not in activated
    with pytest.raises(PairingError, match='pairing_consumed'):
        service.activate_v2(pending['pairing_id'], pending['signing_challenge'], sign(key, pending['signing_challenge']), decrypted)


def test_pairing_rejects_wrong_key_owner_nonce_and_expiry(database):
    from plugins.simulation.simulation_backend.data.connector_app_pairing_repository import SqlAppPairingRepository
    service = PairingService(SqlAppPairingRepository(), clock=lambda: NOW)
    key, jwk, encryption, encryption_jwk = keys()
    nonce = 'nonce-' + database[1]
    pending = service.request_v2(jwk, encryption_jwk, nonce)
    service.bind_v2(pending['pairing_id'], 'user-001', 'tenant-001', expected_version=1)
    for user, tenant in [('user-002', 'tenant-001'), ('user-001', 'tenant-002')]:
        with pytest.raises(PairingError, match='pairing_owner_mismatch'):
            service.bind_v2(pending['pairing_id'], user, tenant, expected_version=2)
    with pytest.raises(PairingError, match='pairing_nonce_reused'):
        service.request_v2(jwk, encryption_jwk, nonce)
    with pytest.raises(PairingError, match='pairing_proof_invalid'):
        service.activate_v2(pending['pairing_id'], pending['signing_challenge'], sign(key, 'wrong'), 'wrong')
    service.clock = lambda: NOW + timedelta(minutes=6)
    with pytest.raises(PairingError, match='pairing_expired'):
        service.activate_v2(pending['pairing_id'], pending['signing_challenge'], sign(key, pending['signing_challenge']), 'wrong')


def test_losing_instance_cannot_evict_winner(database):
    service, key = setup_service(database)
    def attempt(instance):
        try:
            return register(service, key, database[1], instance)
        except RuntimeError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['winner', 'loser']))
    winners = [r for r in results if not isinstance(r, str)]
    assert len(winners) == 1
    assert 'runtime_session_active' in results
    winner = winners[0]
    auth = service.authenticate(winner.session_token, device_id=database[1], generation=7,
                                runtime_instance_id=winner.runtime_instance_id, runtime_type='electron')
    assert auth['current_runtime_instance_id'] == winner.runtime_instance_id
    assert winner.session_token not in str(read(database))
    assert len(base64.urlsafe_b64decode(winner.session_token + '=')) == 32


def test_session_checks_all_identity_pins_and_expiry(database):
    service, key = setup_service(database)
    session = register(service, key, database[1])
    pins = dict(device_id=database[1], generation=7, runtime_instance_id='winner', runtime_type='electron')
    for field, value in [('device_id', 'other'), ('generation', 8), ('runtime_instance_id', 'loser'), ('runtime_type', 'service')]:
        with pytest.raises(RuntimeError):
            service.authenticate(session.session_token, **{**pins, field: value})
    service.clock = lambda: NOW + timedelta(minutes=6)
    with pytest.raises(RuntimeError, match='runtime_session_invalid'):
        service.authenticate(session.session_token, **pins)


def test_registration_rejects_wrong_credential_signature_and_challenge_replay(database):
    service, key = setup_service(database)
    with pytest.raises(RuntimeError, match='device_credential_invalid'):
        service.challenge(database[1], 'wrong', 7, 'winner', runtime_type='electron')
    challenge = service.challenge(database[1], 'device-secret', 7, 'winner', runtime_type='electron')['challenge']
    kwargs = dict(device_credential='device-secret', runtime_type='electron', challenge=challenge)
    with pytest.raises(RuntimeError, match='runtime_proof_invalid'):
        service.register(database[1], 7, 'winner', signature=sign(key, 'wrong'), **kwargs)
    service.register(database[1], 7, 'winner', signature=sign(key, challenge), **kwargs)
    with pytest.raises(RuntimeError, match='runtime_proof_invalid'):
        service.register(database[1], 7, 'winner', signature=sign(key, challenge), **kwargs)


def test_takeover_is_owner_scoped_increments_generation_and_fences_old_session(database):
    service, key = setup_service(database)
    old = register(service, key, database[1])
    with pytest.raises(RuntimeError, match='runtime_owner_mismatch'):
        service.takeover(database[1], 7, 'new', actor_id='other', tenant_id='tenant-001', reason='recover')
    result = service.takeover(database[1], 7, 'new', actor_id='user-001', tenant_id='tenant-001', reason='recover')
    assert result['runtime_generation'] == 8
    assert 'session_token' not in result
    with pytest.raises(RuntimeError, match='runtime_session_invalid'):
        service.authenticate(old.session_token, device_id=database[1], generation=7, runtime_instance_id='winner', runtime_type='electron')


def test_recovery_token_is_plan_scoped_and_cannot_be_normal_session(database):
    service, key = setup_service(database)
    normal = register(service, key, database[1])
    plan = queue(database, normal)
    lease(database, normal)
    service.clock = lambda: NOW + timedelta(minutes=6)
    recovered = register(service, key, database[1], instance='recovery', plan_id=plan.plan_id)
    pins = dict(device_id=database[1], generation=7, runtime_instance_id='recovery', runtime_type='electron')
    with pytest.raises(RuntimeError, match='runtime_session_invalid'):
        service.authenticate(recovered['session_token'], **pins)
    assert service.authenticate_reconciliation(recovered['session_token'], plan_id=plan.plan_id, **pins)['scope'] == 'plan_reconciliation'
    with pytest.raises(RuntimeError):
        service.authenticate_reconciliation(recovered['session_token'], plan_id='other', **pins)


def test_takeover_capability_is_confirmed_and_web_only():
    from backend.capabilities.registry_next import CapabilityRegistry
    from plugins.simulation.simulation_backend.capabilities import register_capabilities
    registry = CapabilityRegistry()
    register_capabilities(registry)
    item = next((r for r in registry.snapshot() if r.spec.id == 'simulation.connector.runtime.takeover'), None)
    assert item is not None
    assert item.spec.confirmation == 'user'
    assert item.spec.risk.value == 'write'
    assert item.descriptor.exposure.web
    assert not item.descriptor.exposure.local_runtime
    assert not item.descriptor.exposure.agent


def test_takeover_requires_reserved_instance_proof_and_exposes_no_secret(database):
    service, key = setup_service(database)
    register(service, key, database[1])
    result = service.takeover(database[1], 7, 'reserved', actor_id='user-001', tenant_id='tenant-001', reason='User recovery')
    assert set(result) == {'device_id', 'runtime_generation', 'runtime_instance_id', 'audit_ref'}
    with pytest.raises(RuntimeError, match='runtime_instance_reserved'):
        register(service, key, database[1], 'other', generation=8)
    winner = register(service, key, database[1], 'reserved', generation=8)
    assert winner.runtime_generation == 8
    assert read(database)['takeover_instance_id'] is None


def test_takeover_rejects_unresolved_work(database):
    service, key = setup_service(database)
    normal = register(service, key, database[1])
    queue(database, normal)
    lease(database, normal)
    with pytest.raises(RuntimeError, match='runtime_plans_unresolved'):
        service.takeover(database[1], 7, 'new', actor_id='user-001', tenant_id='tenant-001', reason='recover')
    assert read(database)['runtime_generation'] == 7

def test_pairing_encrypted_credential_authenticates_device_and_cancellation_is_audited(database):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from plugins.simulation.simulation_backend.application.connector_runtime_sessions import RuntimeSessionService
    from plugins.simulation.simulation_backend.data.connector_app_pairing_repository import SqlAppPairingRepository
    service = PairingService(SqlAppPairingRepository(), clock=lambda: NOW)
    key, jwk, encryption, encryption_jwk = keys()
    pending = service.request_v2(jwk, encryption_jwk, 'nonce-' + database[1])
    service.bind_v2(pending['pairing_id'], 'user-001', 'tenant-001', expected_version=1)
    decode = lambda value: base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    decrypted = encryption.decrypt(decode(pending['encrypted_challenge']), oaep).decode()
    result = service.activate_v2(pending['pairing_id'], pending['signing_challenge'], sign(key, pending['signing_challenge']), decrypted)
    envelope = result['encrypted_credential_envelope']
    secret_key = encryption.decrypt(decode(envelope['encrypted_key']), oaep)
    payload = json.loads(AESGCM(secret_key).decrypt(decode(envelope['nonce']), decode(envelope['ciphertext']), None))
    sessions = RuntimeSessionService(SimulationConnectorRepository(), clock=lambda: NOW)
    challenge = sessions.challenge(payload['device_id'], payload['device_credential'], 1, 'new-app', runtime_type='electron')
    assert challenge['device_key_id'] == result['device_key_id']
    row = sessions.repository.runtime_device(payload['device_id'])
    assert row['device_credential_hash'] == hashlib.sha256(payload['device_credential'].encode()).hexdigest()
    assert payload['device_credential'] not in str(row)
    # A different pending pairing can be cancelled only by its bound owner.
    pending = service.request_v2(jwk, encryption_jwk, 'cancel-' + database[1])
    service.bind_v2(pending['pairing_id'], 'user-001', 'tenant-001', expected_version=1)
    with pytest.raises(PairingError, match='pairing_owner_mismatch'):
        service.cancel_v2(pending['pairing_id'], 'user-001', 'wrong-tenant', expected_version=2)
    assert service.cancel_v2(pending['pairing_id'], 'user-001', 'tenant-001', expected_version=2)['status'] == 'cancelled'
    with pytest.raises(PairingError, match='pairing_consumed'):
        service.activate_v2(pending['pairing_id'], pending['signing_challenge'], sign(key, pending['signing_challenge']), 'unused')
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('SELECT event_type,reason FROM workmanship_sim_connector_runtime_audit WHERE pairing_id=%s', (pending['pairing_id'],))
        events = cur.fetchall()
    assert any(e['event_type'] == 'pairing_cancelled' for e in events)
    assert any(e['reason'] == 'pairing_owner_mismatch' for e in events)


def test_http_runtime_pins_renew_and_recovery_scope_are_enforced(database, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers import simulation_connector as routes
    service, key = setup_service(database)
    monkeypatch.setattr(routes, 'runtime_session_service', service)
    normal = register(service, key, database[1])
    app = FastAPI()
    app.include_router(routes.router)
    headers = {'X-AI00-Device-ID': database[1], 'X-AI00-Runtime-Generation': '7',
               'X-AI00-Runtime-Instance-ID': 'winner', 'X-AI00-Runtime-Type': 'electron',
               'X-AI00-Runtime-Session': normal.session_token}
    prefix = '/api/v1/simulation/connectors/v2/'
    with TestClient(app) as client:
        assert client.post(prefix + 'heartbeat', headers=headers).status_code == 200
        assert client.post(prefix + 'runtime/renew', headers=headers).status_code == 200
        assert client.post(prefix + 'heartbeat', headers={**headers, 'X-AI00-Runtime-Instance-ID': 'loser'}).status_code == 401
        plan = queue(database, normal)
        lease(database, normal)
        service.clock = lambda: NOW + timedelta(minutes=6)
        recovery = register(service, key, database[1], 'recovery', plan_id=plan.plan_id)
        recovery_headers = {**headers, 'X-AI00-Runtime-Instance-ID': 'recovery', 'X-AI00-Runtime-Session': recovery['session_token']}
        for path in ('heartbeat', 'runtime/renew', 'plans/lease'):
            assert client.post(prefix + path, headers=recovery_headers, json={}).status_code == 401
        assert client.get(prefix + f'plans/{plan.plan_id}/probe', headers=recovery_headers).status_code == 200
        assert client.get(prefix + 'plans/another-plan/probe', headers=recovery_headers).status_code != 200
        assert client.post(prefix + f'plans/{plan.plan_id}/outcome', headers=recovery_headers, json={}).status_code == 401
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect(prefix + 'plans/wake', headers=recovery_headers):
                pass
        assert rejected.value.code == 4401


def test_takeover_capability_response_and_evidence_are_secret_free(database):
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import ConnectorControlPlane, register_connector_runtime_capabilities
    service, key = setup_service(database)
    old = register(service, key, database[1])
    registry = CapabilityRegistry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(service.repository, clock=lambda: NOW))
    item = next(r for r in registry.snapshot() if r.spec.id == 'simulation.connector.runtime.takeover')
    result = item.handler({'device_id': database[1], 'expected_generation': 7, 'runtime_instance_id': 'reserved', 'reason': 'recover'},
                         CapabilityContext(user_gid='user-001', team_gid='tenant-001', source='web'))
    encoded = str(result)
    assert old.session_token not in encoded
    assert 'device-secret' not in encoded
    assert 'session_token' not in encoded
    assert 'credential_envelope' not in encoded

def test_takeover_gateway_fails_without_server_approval_before_state_change(database):
    import asyncio
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.authorization import AuthorizationGrants
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.contracts import ActorIdentity, TenantIdentity, ConsumerIdentity, ConsumerDescriptor, ConsumerType, InvocationEnvelope
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import ConnectorControlPlane, register_connector_runtime_capabilities
    service, key = setup_service(database)
    normal = register(service, key, database[1])
    registry = CapabilityRegistry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(service.repository, clock=lambda: NOW))
    item = registry.get('simulation.connector.runtime.takeover', 1)
    release = build_release([item.descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)
    policy = LegacyServerGatewayPolicy(user_loader=lambda _: {'is_active': True},
        grants_resolver=lambda *_: AuthorizationGrants(permissions=('simulation.use',), data_scopes=('confidential',),
            policy_version='test-policy', tenant_id='tenant-001'))
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.reliability import ReliabilityCoordinator, InMemoryRateLimiter
    gateway = CapabilityGatewayService(CatalogResolver(store, registry), policy, reliability=ReliabilityCoordinator(
        InMemoryOutcomeStore(), InMemoryRateLimiter(limit=10))).bind_release(release.release_id)
    identity = ConsumerIdentity(actor=ActorIdentity(user_id='user-001', authentication_method='web', authenticated_at=NOW),
        tenant=TenantIdentity(tenant_id='tenant-001', membership='member'), consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id='ai00.web.simulation'))
    result = asyncio.run(gateway.invoke(InvocationEnvelope(capability_id=item.spec.id, major_version=1,
        catalog_release=release.release_id, payload={'device_id': database[1], 'expected_generation': 7,
            'runtime_instance_id': 'replacement', 'reason': 'recovery'}, identity=identity,
        request_id='req-takeover', trace_id='trace-takeover', idempotency_key='idem-takeover')))
    assert not result.ok
    assert result.error.code == 'approval_service_unavailable'
    assert read(database)['runtime_generation'] == normal.runtime_generation


def test_0009_migration_is_additive_and_passes_owner_policy():
    from pathlib import Path
    from backend.db.versioned_migrations import Migration, validate_migration
    from backend.governance import load_registry
    path = Path(__file__).resolve().parents[1] / 'db/migrations/domains/simulation/0009_connector_app_auth.sql'
    sql = path.read_text()
    validate_migration(Migration('0009', 'simulation', 'connector_app_auth', path, sql, hashlib.sha256(sql.encode()).hexdigest()), load_registry())
    assert 'DROP TABLE' not in sql
    assert 'DELETE FROM' not in sql

def test_v2_pairing_capability_publishes_closed_datetime_output(database, monkeypatch):
    from jsonschema import Draft202012Validator, FormatChecker
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.simulation.simulation_backend.capabilities import connector_pairing as provider
    from plugins.simulation.simulation_backend.capabilities.provider import governed_spec
    from plugins.simulation.simulation_backend.data.connector_app_pairing_repository import SqlAppPairingRepository
    service = PairingService(SqlAppPairingRepository(), clock=lambda: NOW)
    monkeypatch.setattr(provider, 'app_pairing_service', service)
    _, jwk, _, encryption = keys()
    pending = service.request_v2(jwk, encryption, 'nonce-' + database[1])
    spec, handler = next((s, h) for s, h in provider.specs() if s.id == 'simulation.connector.pairing.approve' and s.version == 2)
    result = handler({'pairing_id': pending['pairing_id'], 'expected_version': 1}, CapabilityContext(user_gid='user-001', team_gid='tenant-001', source='web'))
    assert result.data["expires_at"] == (NOW + timedelta(minutes=5)).isoformat()
    Draft202012Validator(governed_spec(spec).output_schema, format_checker=FormatChecker()).validate(result.data)
