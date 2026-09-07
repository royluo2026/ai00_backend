"""Cloud v2 trust boundaries exercised with real ECDSA and SQL transactions."""
from copy import deepcopy
from datetime import timedelta
import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from backend.contracts.connector_execution_plan_v2 import (
    ConnectorPlanOutcomeV2, P256_ORDER, canonicalize_v2, outcome_signature_bytes,
)
from backend.tests.test_simulation_connector_runtime_v2_sql import database, ROOT, NOW, read
from backend.tests.test_connector_runtime_sessions_v2 import setup_service, register

VECTOR = json.loads((ROOT / 'backend/tests/fixtures/connector_execution_plan_v2.json').read_text())


def signature(key, data):
    r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
    return base64.urlsafe_b64encode(r.to_bytes(32, 'big') + min(s, P256_ORDER-s).to_bytes(32, 'big')).rstrip(b'=').decode()


def signer():
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import PlanSigner
    key = ec.generate_private_key(ec.SECP256R1())
    record = dict(private_key=key, not_before=NOW-timedelta(days=1), not_after=NOW+timedelta(days=1), revoked=False)
    return PlanSigner(lambda key_id: record, key_id='cloud-key', clock=lambda: NOW), record


def test_public_key_cannot_mint_cloud_plans_and_final_bindings_are_signed():
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import PlanSigner
    service, record = signer()
    raw = deepcopy(VECTOR['plan'])
    raw.update(issued_at='2026-09-07T12:00:00Z', expires_at='2026-09-07T12:10:00Z')
    signed = service.sign(raw)
    p = record['private_key'].public_key().public_numbers()
    b64 = lambda x: base64.urlsafe_b64encode(x.to_bytes(32, 'big')).rstrip(b'=').decode()
    public = dict(kty='EC', crv='P-256', x=b64(p.x), y=b64(p.y))
    assert signed.verify_signature(public)
    assert signed.key_id == 'cloud-key'
    assert not signed.model_copy(update={'runtime_instance_id': 'attacker'}).verify_signature(public)
    with pytest.raises(ValueError, match='cloud_secret_provider_required'):
        PlanSigner.from_jwk(public)
    record['private_key'] = record['private_key'].public_key()
    with pytest.raises(ValueError, match='private_key_required'):
        service.sign(raw)


@pytest.mark.parametrize('changes', [dict(revoked=True), dict(not_before=NOW+timedelta(seconds=1)), dict(not_after=NOW)])
def test_signing_key_revocation_and_validity_are_enforced(changes):
    service, record = signer()
    record.update(changes)
    with pytest.raises(ValueError, match='signing_key_inactive'):
        service.sign(VECTOR['plan'])


def running(database, *, probe=True, plan_id=None):
    service, key = setup_service(database)
    session = register(service, key, database[1])
    cloud, _ = signer()
    raw = deepcopy(VECTOR['plan'])
    raw.update(plan_id=plan_id or 'v2-'+database[1], device_id=database[1], runtime_instance_id='winner',
               issued_at='2026-09-07T12:00:00Z', expires_at='2026-09-07T12:10:00Z')
    if probe:
        raw['steps'][0].update(side_effect_classification='write', post_condition_probe_id='vismockup.application.postcondition@1')
    plan = cloud.sign(raw)
    service.repository.insert_v2_plan(plan, session.session_token, NOW)
    pins = dict(device_id=database[1], generation=7, runtime_instance_id='winner', runtime_type='electron')
    leased = service.lease(session.session_token, **pins)
    return service, key, session, plan, leased, pins


def outcome(plan, leased, key, status='succeeded', sequence=1, result=None, **changes):
    raw = deepcopy(VECTOR['outcome'])
    raw.update(plan_id=plan.plan_id, device_id=plan.device_id, plan_hash=plan.plan_hash,
               lease_id=leased['lease_id'], runtime_instance_id=plan.runtime_instance_id,
               device_key_id='device-key-001', overall_status=status, journal_sequence=sequence)
    step = raw['steps'][0]
    step.update(status=status, result=result or {}, error_code=None if status=='succeeded' else 'execution_uncertain',
                reconciliation_state='pending' if status=='outcome_unknown' else 'not_required')
    step['result_hash'] = 'sha256:'+hashlib.sha256(canonicalize_v2(step['result'])).hexdigest() if status=='succeeded' else None
    raw.update(changes)
    raw['signature'] = signature(key, outcome_signature_bytes(raw))
    return ConnectorPlanOutcomeV2.model_validate(raw)


def probe_evidence(context, key, classification='failed_without_effect', sequence=2, *, probes=None):
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import ConnectorReconciliationEvidenceV2
    raw = {k: context[k] for k in ('plan_id','plan_hash','lease_id','tenant_id','device_id',
        'runtime_generation','runtime_instance_id','recovery_instance_id','recovery_session_id','nonce','scope')}
    raw.update(protocol='ai00.connector.reconciliation-evidence.v2', journal_sequence=sequence,
        reported_at='2026-09-07T12:06:00Z', device_key_id='device-key-001', signature_algorithm='ecdsa-p256-sha256',
        probes=probes if probes is not None else [dict(**p, classification=classification, observed_result=None) for p in context['required_probes']])
    raw['signature'] = signature(key, outcome_signature_bytes(raw))
    return ConnectorReconciliationEvidenceV2.model_validate(raw)


@pytest.mark.parametrize('crash,read_prefix,classification,coverage,expected', [
    (False, False, 'failed_without_effect', 'all', 'failed_without_effect'),
    (False, True, 'failed_without_effect', 'all', 'failed_without_effect'),
    (True, False, 'failed_without_effect', 'all', 'failed_without_effect'),
    (True, True, 'failed_without_effect', 'all', 'failed_without_effect'),
    (True, False, 'succeeded', 'all', 'succeeded'),
    (False, False, 'succeeded', 'all', 'manual_review_required'),
    (True, True, 'failed_without_effect', 'missing', 'manual_review_required'),
    (True, True, 'failed_without_effect', 'mixed', 'manual_review_required'),
    (True, False, 'inconclusive', 'all', 'manual_review_required'),
])
def test_dedicated_evidence_reconciles_multiple_writes_without_execution_prefix(database, crash, read_prefix, classification, coverage, expected):
    service, key = setup_service(database)
    session = register(service, key, database[1])
    cloud, _ = signer()
    raw = deepcopy(VECTOR['plan'])
    raw.update(device_id=database[1], runtime_instance_id='winner', issued_at='2026-09-07T12:00:00Z', expires_at='2026-09-07T12:10:00Z')
    first = raw['steps'][0]
    raw['steps'] = ([deepcopy(first)] if read_prefix else []) + [dict(deepcopy(first),
        step_id=f'write-{i}', side_effect_classification='write', post_condition_probe_id=f'write.{i}.probe@1') for i in range(2)]
    if read_prefix and not crash:
        raw['steps'][0]['post_condition_probe_id'] = 'read.check@1'
    plan = cloud.sign(raw)
    service.repository.insert_v2_plan(plan, session.session_token, NOW)
    pins = dict(device_id=database[1], generation=7, runtime_instance_id='winner', runtime_type='electron')
    leased = service.lease(session.session_token, **pins)
    original = None
    if not crash:
        raw_outcome = outcome(plan, leased, key, 'outcome_unknown').model_dump(mode='json')
        raw_outcome['steps'][0]['step_id'] = 'write-0'
        if read_prefix:
            terminal = deepcopy(raw_outcome['steps'][0])
            raw_outcome['steps'] = []
            for step in plan.steps:
                result = dict(terminal, step_id=step.step_id)
                if step is not plan.steps[-1]:
                    result.update(status='succeeded', error_code=None, result={},
                        result_hash='sha256:'+hashlib.sha256(b'{}').hexdigest())
                raw_outcome['steps'].append(result)
        raw_outcome['signature'] = signature(key, outcome_signature_bytes(raw_outcome))
        original = ConnectorPlanOutcomeV2.model_validate(raw_outcome)
        service.outcome(session.session_token, original, **pins)
    service.clock = lambda: NOW+timedelta(minutes=6)
    recovered = register(service, key, database[1], instance='replacement', plan_id=plan.plan_id)
    pins['runtime_instance_id'] = 'replacement'
    context = service.probe(recovered['session_token'], plan_id=plan.plan_id, **pins)
    assert context['recovery_instance_id'] == 'replacement'
    assert context['lease_id'] == leased['lease_id']
    assert 'steps' not in context and 'plan' not in context
    assert [p['step_id'] for p in context['required_probes']] == (['write-0', 'write-1'] if crash or read_prefix else ['write-0'])
    probes = [dict(**p, classification=classification, observed_result=None) for p in context['required_probes']]
    if coverage == 'missing':
        probes = probes[:-1]
    elif coverage == 'mixed':
        probes[-1]['classification'] = 'succeeded'
    evidence = probe_evidence(context, key, probes=probes)
    service.outcome(recovered['session_token'], evidence, reconcile=True, **pins)
    saved = json.loads(read(database, 'runtime_plans')['outcome_json'])
    assert saved['overall_status'] == expected
    assert 'signature' not in saved
    assert saved['evidence'] == evidence.model_dump(mode='json')
    assert saved['original_outcome'] == (original.model_dump(mode='json') if original else None)


def test_reconciliation_evidence_is_closed_and_context_signature_bound(database):
    from pydantic import ValidationError
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import ConnectorReconciliationEvidenceV2
    service, key, session, plan, leased, pins = running(database)
    service.outcome(session.session_token, outcome(plan, leased, key, 'outcome_unknown'), **pins)
    context = service.probe(session.session_token, plan_id=plan.plan_id, **pins)
    evidence = probe_evidence(context, key)
    raw = evidence.model_dump(mode='json')
    for field in raw:
        with pytest.raises(ValidationError):
            ConnectorReconciliationEvidenceV2.model_validate({k:v for k,v in raw.items() if k != field})
    with pytest.raises(ValidationError):
        ConnectorReconciliationEvidenceV2.model_validate({**raw, 'steps':[]})
    for field, value in [('nonce','0'*64), ('recovery_session_id','0'*64), ('recovery_instance_id','other')]:
        changed = {**raw, field:value}
        changed['signature'] = signature(key, outcome_signature_bytes(changed))
        with pytest.raises(RuntimeError, match='reconciliation_evidence_invalid'):
            service.outcome(session.session_token, ConnectorReconciliationEvidenceV2.model_validate(changed), reconcile=True, **pins)
    wrong = probe_evidence(context, ec.generate_private_key(ec.SECP256R1()))
    with pytest.raises(RuntimeError, match='outcome_signature_invalid'):
        service.outcome(session.session_token, wrong, reconcile=True, **pins)
    assert read(database)['last_journal_sequence'] == 1


def test_outcome_verifies_device_key_and_persists_projection_atomically(database):
    service, key, session, plan, leased, pins = running(database)
    bad = outcome(plan, leased, key, device_key_id='unregistered-key')
    with pytest.raises(RuntimeError, match='device_key_invalid'):
        service.outcome(session.session_token, bad, **pins)
    assert read(database, 'runtime_plans')['outcome_hash'] is None
    good = outcome(plan, leased, key)
    service.outcome(session.session_token, good, **pins)
    service.outcome(session.session_token, good, **pins)
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('SELECT status FROM workmanship_sim_connector_runtime_projection_outbox WHERE plan_id=%s', (plan.plan_id,))
        assert cur.fetchone()['status'] == 'pending'
    assert read(database)['last_journal_sequence'] == 1


def test_unknown_outcome_blocks_equivalent_normalized_input(database):
    service, key, session, plan, leased, pins = running(database)
    service.outcome(session.session_token, outcome(plan, leased, key, 'outcome_unknown'), **pins)
    cloud, _ = signer()
    replacement = cloud.sign({**plan.model_dump(mode='json'), 'plan_id':'replacement', 'idempotency_key':'new-key'})
    with pytest.raises(RuntimeError, match='reconciliation_required'):
        service.repository.insert_v2_plan(replacement, session.session_token, NOW)


def test_recovery_context_binds_original_lease_and_never_returns_mutation(database):
    service, key, session, plan, leased, pins = running(database)
    service.clock = lambda: NOW+timedelta(minutes=6)
    recovered = register(service, key, database[1], instance='recovery', plan_id=plan.plan_id)
    pins['runtime_instance_id'] = 'recovery'
    context = service.probe(recovered['session_token'], plan_id=plan.plan_id, **pins)
    assert context['lease_id'] == leased['lease_id']
    assert context['scope'] == 'read_only_post_condition_probe'
    assert 'steps' not in context and 'plan' not in context
    assert context['required_probes'][0]['probe_id'] == 'vismockup.application.postcondition@1'
    assert context['nonce']
    forged = outcome(plan, leased, key, sequence=2)
    with pytest.raises(RuntimeError, match='reconciliation_evidence_invalid'):
        service.outcome(recovered['session_token'], forged, reconcile=True, **pins)


@pytest.mark.parametrize('classification', ['succeeded', 'failed_without_effect', 'inconclusive'])
def test_signed_probe_controls_reconciliation_and_replacement(database, classification):
    service, key, session, plan, leased, pins = running(database)
    service.outcome(session.session_token, outcome(plan, leased, key, 'outcome_unknown'), **pins)
    service.clock = lambda: NOW+timedelta(minutes=6)
    recovered = register(service, key, database[1], instance='recovery', plan_id=plan.plan_id)
    pins['runtime_instance_id'] = 'recovery'
    context = service.probe(recovered['session_token'], plan_id=plan.plan_id, **pins)
    status = 'manual_review_required' if classification=='inconclusive' else classification
    evidence = probe_evidence(context, key, classification)
    service.outcome(recovered['session_token'], evidence, reconcile=True, **pins)
    assert read(database, 'runtime_plans')['status'] == status
    assert read(database)['last_journal_sequence'] == 2
    if classification != 'inconclusive':
        fresh = register(service, key, database[1], instance='replacement')
        cloud, _ = signer()
        replacement = cloud.sign({**plan.model_dump(mode='json'), 'plan_id':'replacement',
            'idempotency_key':'replacement', 'runtime_instance_id':'replacement'})
        if classification == 'failed_without_effect':
            service.repository.insert_v2_plan(replacement, fresh.session_token, service.clock())
        else:
            with pytest.raises(RuntimeError, match='reconciliation_required'):
                service.repository.insert_v2_plan(replacement, fresh.session_token, service.clock())


def test_absent_probe_classifies_manual_review():
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import ReconciliationService
    assert ReconciliationService().reconcile('plan-1', None) == 'manual_review_required'


def test_worker_reads_verified_v2_payload_and_finishes_projection(database):
    import asyncio
    from plugins.simulation.simulation_backend.application.connector_projection_worker import ConnectorProjectionWorker
    from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository
    service, key, session, plan, leased, pins = running(database)
    good = outcome(plan, leased, key)
    service.outcome(session.session_token, good, **pins)
    calls = []
    class Projector:
        def target(self, value):
            return 'simulation.connector_materialization_outcome.apply'
        async def apply(self, value, result, **kwargs):
            assert value == plan and result == good
            calls.append(value.plan_id)
    worker = ConnectorProjectionWorker(SimulationConnectorRepository(projection_protocol=plan.protocol), Projector(), owner='v2-worker')
    assert asyncio.run(worker.run_once()) is True
    assert calls == [plan.plan_id]
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('SELECT status FROM workmanship_sim_connector_runtime_projection_outbox WHERE plan_id=%s', (plan.plan_id,))
        assert cur.fetchone()['status'] == 'projected'


def test_bad_signature_and_sequence_leave_no_partial_state(database):
    service, key, session, plan, leased, pins = running(database)
    good = outcome(plan, leased, key)
    bad = outcome(plan, leased, ec.generate_private_key(ec.SECP256R1()))
    with pytest.raises(RuntimeError, match='outcome_signature_invalid'):
        service.repository.complete_v2_plan(database[1], 7, 'winner', session.session_token, bad, NOW)
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_devices SET last_journal_sequence=1 WHERE device_id=%s', (database[1],))
    with pytest.raises(RuntimeError, match='journal_sequence_invalid'):
        service.outcome(session.session_token, good, **pins)
    assert read(database, 'runtime_plans')['outcome_hash'] is None


def test_projection_and_journal_roll_back_with_outcome_when_audit_insert_fails(database, monkeypatch):
    from types import SimpleNamespace
    import sqlite3
    import pymysql
    from plugins.simulation.simulation_backend.data import connector_repository
    service, key, session, plan, leased, pins = running(database)
    audit_id = read(database, 'runtime_audit')['audit_id']
    monkeypatch.setattr(connector_repository.uuid, 'uuid4', lambda: SimpleNamespace(hex=audit_id))
    with pytest.raises((sqlite3.IntegrityError, pymysql.IntegrityError)):
        service.outcome(session.session_token, outcome(plan, leased, key), **pins)
    assert read(database, 'runtime_plans')['outcome_hash'] is None
    assert read(database)['last_journal_sequence'] == 0
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('SELECT plan_id FROM workmanship_sim_connector_runtime_projection_outbox WHERE plan_id=%s', (plan.plan_id,))
        assert cur.fetchone() is None


def test_no_declared_probe_keeps_recovery_in_manual_review(database):
    service, key, session, plan, leased, pins = running(database, probe=False)
    service.clock = lambda: NOW+timedelta(minutes=6)
    recovered = register(service, key, database[1], instance='recovery', plan_id=plan.plan_id)
    pins['runtime_instance_id'] = 'recovery'
    context = service.probe(recovered['session_token'], plan_id=plan.plan_id, **pins)
    assert context['required_probes'] == []
    evidence = probe_evidence(context, key, 'inconclusive', sequence=1)
    service.outcome(recovered['session_token'], evidence, reconcile=True, **pins)
    assert read(database, 'runtime_plans')['status'] == 'manual_review_required'


def test_current_session_can_probe_unknown_effect_with_server_lease_context(database):
    service, key, session, plan, leased, pins = running(database)
    service.outcome(session.session_token, outcome(plan, leased, key, 'outcome_unknown'), **pins)
    context = service.probe(session.session_token, plan_id=plan.plan_id, **pins)
    assert context['lease_id'] == leased['lease_id']
    evidence = probe_evidence(context, key)
    service.outcome(session.session_token, evidence, reconcile=True, **pins)
    assert read(database, 'runtime_plans')['status'] == 'failed_without_effect'


def test_0010_migration_matches_simulation_ownership():
    from backend.db.versioned_migrations import Migration, validate_migration
    from backend.governance import load_registry
    path = ROOT / 'backend/db/migrations/domains/simulation/0010_connector_v2_projection.sql'
    sql = path.read_text()
    validate_migration(Migration('0010', 'simulation', 'connector_v2_projection', path, sql, hashlib.sha256(sql.encode()).hexdigest()), load_registry())


def test_queue_v2_pins_owner_before_signing(database):
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import ConnectorControlPlane, ConnectorError
    service, key = setup_service(database)
    normal = register(service, key, database[1])
    cloud, _ = signer()
    control = ConnectorControlPlane(service.repository, plan_signer=cloud, clock=lambda: NOW)
    raw = deepcopy(VECTOR['plan'])
    raw.update(device_id=database[1], issued_at='2026-09-07T12:00:00Z', expires_at='2026-09-07T12:10:00Z')
    with pytest.raises(ConnectorError, match='plan_identity_mismatch'):
        control.queue_v2(raw, CapabilityContext(user_gid='other', team_gid='tenant-001'), normal.session_token)
    control.queue_v2(raw, CapabilityContext(user_gid='user-001', team_gid='tenant-001'))
    persisted = json.loads(read(database, 'runtime_plans')['plan_json'])
    assert persisted['runtime_instance_id'] == 'winner'
    assert persisted['key_id'] == 'cloud-key'


@pytest.mark.parametrize('plan_id_length', [184, 256])
@pytest.mark.parametrize('reconciled', [False, True])
def test_verified_v2_materialization_projects_exact_persisted_plan(database, plan_id_length, reconciled):
    import asyncio
    from types import SimpleNamespace
    from plugins.simulation.simulation_backend.application.capture_worker import CaptureWorkflow
    from plugins.simulation.simulation_backend.capabilities.connector_outcomes import ConnectorOutcomeProvider
    from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityBusinessError
    service, key, session, plan, leased, pins = running(database, plan_id='p'*plan_id_length)
    good = outcome(plan, leased, key, 'outcome_unknown' if reconciled else 'succeeded')
    service.outcome(session.session_token, good, **pins)
    if reconciled:
        context = service.probe(session.session_token, plan_id=plan.plan_id, **pins)
        service.outcome(session.session_token, probe_evidence(context, key, 'succeeded'), reconcile=True, **pins)
        from plugins.simulation.simulation_backend.application.connector_protocol_v2 import parse_v2_outcome
        good = parse_v2_outcome(json.loads(read(database, 'runtime_plans')['outcome_json']))
    changes = []
    repo = SimpleNamespace(get_materialization_run=lambda *a: {'plan': plan.model_dump(mode='json')},
                           update_materialization_run=lambda *a, **kw: changes.append(kw))
    workflow = object.__new__(CaptureWorkflow)
    workflow.repository = repo
    payload = dict(run_id=plan.plan_id, plan_json=plan.model_dump_json(), outcome_json=good.model_dump_json())
    provider = ConnectorOutcomeProvider(workflow, None)
    with pytest.raises(CapabilityBusinessError, match='projection_unverified'):
        asyncio.run(provider.apply_materialization(payload, CapabilityContext(user_gid='user-001', team_gid='tenant-001')))
    from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository
    outbox = SimulationConnectorRepository(projection_protocol=plan.protocol)
    claimed = outbox.claim_projection('worker')
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy, AuthorizationGrants
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.reliability import ReliabilityCoordinator, InMemoryRateLimiter
    from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient
    from plugins.simulation.simulation_backend.capabilities.connector_outcomes import specs
    from plugins.simulation.simulation_backend.capabilities.provider import register as register_provider
    registry = CapabilityRegistry()
    for spec, handler in specs(provider):
        register_provider(registry, spec, handler)
    release = build_release([registry.get('simulation.connector_materialization_outcome.apply', 1).descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)
    policy = LegacyServerGatewayPolicy(user_loader=lambda _: {'is_active':True},
        grants_resolver=lambda *_: AuthorizationGrants(permissions=('simulation.use',), data_scopes=('confidential',),
            policy_version='test-policy', tenant_id='tenant-001'), resource_authorizer=lambda *_: True)
    gateway = CapabilityGatewayService(CatalogResolver(store, registry), policy,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100))).bind_release(release.release_id)
    invoked = []
    invoke = gateway.invoke
    async def record(envelope):
        invoked.append(envelope)
        return await invoke(envelope)
    gateway.invoke = record
    asyncio.run(GovernedSimulationRuntimeClient(gateway).apply_connector_outcome(plan, good))
    assert changes == [{'status': 'completed'}]
    assert claimed.plan_id == plan.plan_id
    assert len(invoked[0].trace_id) == 79
    assert len(invoked[0].idempotency_key) == 85
    assert len(invoked[0].request_id) <= 128
    assert invoked[0].trace_id.endswith(hashlib.sha256(plan.plan_id.encode()).hexdigest())
    outcome_hash = 'sha256:' + hashlib.sha256(json.dumps(good.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',',':')).encode()).hexdigest()
    assert invoked[0].idempotency_key.endswith(hashlib.sha256((plan.plan_id+'\0'+outcome_hash).encode()).hexdigest())


def test_http_reconciliation_accepts_only_dedicated_evidence(database, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers import simulation_connector
    service, key, session, plan, leased, pins = running(database)
    original = outcome(plan, leased, key, 'outcome_unknown')
    service.outcome(session.session_token, original, **pins)
    context = service.probe(session.session_token, plan_id=plan.plan_id, **pins)
    evidence = probe_evidence(context, key)
    app = FastAPI()
    app.include_router(simulation_connector.router)
    monkeypatch.setattr(simulation_connector, 'runtime_session_service', service)
    app.dependency_overrides[simulation_connector._reconciliation_auth] = lambda: dict(token=session.session_token, **pins)
    app.dependency_overrides[simulation_connector._runtime_auth] = lambda: dict(token=session.session_token, **pins)
    path = '/api/v1/simulation/connectors/v2/plans/' + plan.plan_id
    with TestClient(app) as client:
        assert client.post(path+'/reconcile', json=original.model_dump(mode='json')).status_code == 422
        assert client.post(path+'/outcome', json=evidence.model_dump(mode='json')).status_code == 422
        result = client.post(path+'/reconcile', json=evidence.model_dump(mode='json'))
        assert result.status_code == 200, result.text
    assert read(database, 'runtime_plans')['status'] == 'failed_without_effect'


@pytest.mark.parametrize('valid_snapshot', [True, False])
def test_reconciled_snapshot_projects_observed_result(valid_snapshot):
    from types import SimpleNamespace
    from backend.tests.test_simulation_document_snapshot_workflow import SNAPSHOT, context
    from plugins.simulation.simulation_backend.application.document_snapshots import DocumentSnapshotWorkflow
    cloud, _ = signer()
    raw = deepcopy(VECTOR['plan'])
    raw.update(issued_at='2026-09-07T12:00:00Z', expires_at='2026-09-07T12:10:00Z')
    raw['steps'][0].update(operation_id='vismockup.document.snapshot@1', post_condition_probe_id='snapshot.probe@1')
    plan = cloud.sign(raw)
    recorded = []
    repo = SimpleNamespace(get_request=lambda *a: {'plan':plan.model_dump(mode='json')},
        complete_request=lambda *a, **kw: recorded.append(kw))
    workflow = object.__new__(DocumentSnapshotWorkflow)
    workflow.repository = repo
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import probe_context, ReconciliationService
    from backend.tests.test_connector_runtime_sessions_v2 import keys
    key, jwk, _, _ = keys()
    row = dict(plan_json=plan.model_dump(mode='json'), plan_id=plan.plan_id, plan_hash=plan.plan_hash,
        lease_id='lease-1', device_id=plan.device_id, tenant_gid=plan.tenant_id,
        runtime_generation=plan.runtime_generation, runtime_instance_id=plan.runtime_instance_id)
    recovery = dict(token_hash='a'*64, recovery_instance_id='replacement')
    context_value = probe_context(row, recovery)
    evidence = probe_evidence(context_value, key, 'succeeded', probes=[dict(**context_value['required_probes'][0],
        classification='succeeded', observed_result=SNAPSHOT if valid_snapshot else {})])
    value = ReconciliationService().verify(row, recovery, evidence, jwk)
    workflow.apply_connector_outcome(plan, value, context())
    if valid_snapshot:
        assert value.overall_status == 'succeeded'
        assert recorded[0]['snapshot'] == SNAPSHOT
    else:
        assert value.overall_status == 'manual_review_required'
        assert recorded[0]['status'] == 'outcome_unknown'
