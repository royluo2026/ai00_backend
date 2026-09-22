import base64
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from backend.contracts.connector_execution_plan_v2 import canonicalize_v2, P256_ORDER
from backend.tests.test_viewer_interaction_repository import grant_case, authorize
from plugins.simulation.tests.test_viewer_interaction_authorization import signing, NOW


def seal(batch, signing, prefix=b'ai00.viewer.interaction.events.v1\n'):
    batch = deepcopy(batch)
    batch.pop('signature', None)
    r, s = decode_dss_signature(signing[1]['private_key'].sign(prefix + canonicalize_v2(batch), ec.ECDSA(hashes.SHA256())))
    batch['signature'] = base64.urlsafe_b64encode(r.to_bytes(32, 'big') + min(s, P256_ORDER-s).to_bytes(32, 'big')).rstrip(b'=').decode()
    return batch


@pytest.fixture
def audit_case(grant_case, signing):
    case = grant_case
    grant = authorize(case, signing[0])
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute('ALTER TABLE workmanship_sim_connector_runtime_devices ADD COLUMN device_signing_jwk TEXT')
        cur.execute('ALTER TABLE workmanship_sim_connector_runtime_devices ADD COLUMN device_key_id TEXT')
        cur.execute('UPDATE workmanship_sim_connector_runtime_devices SET session_token_hash=%s,device_signing_jwk=%s,device_key_id=%s',
            (hashlib.sha256(b'current-token').hexdigest(), json.dumps(signing[2]), 'device-key'))
    case.pins = dict(device_id='device-1', generation=1, runtime_instance_id='runtime-1', runtime_type='electron', token='current-token')
    event = dict(grant_id=grant.grant_id, interaction_id=grant.session_nonce, request_id='request-1', sequence=1,
        request_digest='sha256:'+'d'*64, operation_id='vismockup.node.visibility.change@1',
        outcome=dict(request_id='request-1', status='completed', result=dict(targets=[dict(node_ref='opaque-1', status='completed', error_code=None)]),
            error_code=None, timings=dict(total_ms=20, com_ms=10, journal_ms=1)))
    case.batch = dict(protocol='ai00.viewer.interaction.events.v1', device_id='device-1', runtime_instance_id='runtime-1',
        device_key_id='device-key', events=[event])
    return case


def append(case, batch, now=NOW):
    assert hasattr(case.repository, 'append_events'), 'device authenticated transactional audit receiver missing'
    return case.repository.append_events(batch, pins=case.pins, now=now)


@pytest.mark.parametrize('change', ['missing', 'tampered', 'signed-digest', 'wrong-operation'])
def test_audit_requires_untampered_persisted_grant_operation(audit_case, signing, change):
    case = audit_case
    with case.connect() as conn, conn.cursor() as cur:
        if change == 'missing':
            cur.execute('DELETE FROM workmanship_sim_viewer_grant_evidence')
        elif change == 'tampered':
            cur.execute("UPDATE workmanship_sim_viewer_grant_evidence SET proof_digest='bad'")
        else:
            cur.execute('SELECT proof_json FROM workmanship_sim_viewer_grant_evidence')
            proof = json.loads(cur.fetchone()['proof_json'])
            if change == 'signed-digest':
                proof['signed_grant']['document_gid'] = '21'
            else:
                unsigned = proof['signed_grant']
                unsigned.pop('signature')
                unsigned.pop('key_id')
                unsigned['operations'] = [unsigned['operations'][1]]
                proof['signed_grant'] = signing[0].sign_interaction_grant(unsigned).model_dump(mode='json')
                proof['signed_grant_digest'] = 'sha256:' + hashlib.sha256(canonicalize_v2(proof['signed_grant'])).hexdigest()
                proof['operation_bindings'] = [proof['operation_bindings'][1]]
            encoded = canonicalize_v2(proof)
            cur.execute('UPDATE workmanship_sim_viewer_grant_evidence SET proof_json=%s,proof_digest=%s',
                (encoded.decode(), hashlib.sha256(encoded).hexdigest()))
    with pytest.raises(ValueError, match='interaction_audit_(proof_invalid|operation_forbidden)'):
        append(case, seal(case.batch, signing))
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS n FROM workmanship_sim_viewer_interaction_events')
        assert cur.fetchone()['n'] == 0


def test_historical_audit_uses_persisted_operations_not_current_constants(audit_case, signing, monkeypatch):
    from plugins.simulation.simulation_backend.capabilities import connector_runtime
    monkeypatch.setattr(connector_runtime, 'DIRECT_VISMOCKUP_OPERATIONS', {})
    assert append(audit_case, seal(audit_case.batch, signing)) == {'acknowledged_request_ids': ['request-1']}


def test_missing_proof_on_second_event_rolls_back_first_event(audit_case, signing):
    from backend.tests.test_viewer_interaction_repository import request
    case = audit_case
    original_id = case.batch['events'][0]['grant_id']
    second = authorize(case, signing[0], {**request(case), 'prior_grant_id': original_id})
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM workmanship_sim_viewer_grant_evidence WHERE grant_id=%s', (second.grant_id,))
    event = deepcopy(case.batch['events'][0])
    event.update(grant_id=second.grant_id, request_id='request-2', sequence=2)
    event['outcome']['request_id'] = 'request-2'
    case.batch['events'].append(event)
    with pytest.raises(ValueError, match='interaction_audit_proof_invalid'):
        append(case, seal(case.batch, signing))
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS n FROM workmanship_sim_viewer_interaction_events')
        assert cur.fetchone()['n'] == 0


def test_expired_grant_old_runtime_upload_is_idempotent_under_current_device_auth(audit_case, signing):
    case = audit_case
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='runtime-2',runtime_generation=2")
    case.pins.update(runtime_instance_id='runtime-2', generation=2)
    case.batch['runtime_instance_id'] = 'runtime-2'
    batch = seal(case.batch, signing)
    assert append(case, batch, NOW + timedelta(seconds=61)) == {'acknowledged_request_ids':['request-1']}
    assert append(case, batch, NOW + timedelta(seconds=62)) == {'acknowledged_request_ids':['request-1']}
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS n FROM workmanship_sim_viewer_interaction_events')
        assert cur.fetchone()['n'] == 1


@pytest.mark.parametrize('change', ['tenant', 'device', 'nonce', 'auth', 'signature-domain', 'outcome-id', 'busy', 'extra', 'oversize'])
def test_audit_rejects_forgery_unfinalized_and_unbounded_events(audit_case, signing, change):
    case = audit_case
    batch = deepcopy(case.batch)
    event = batch['events'][0]
    if change == 'tenant':
        with case.connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE workmanship_sim_viewer_source_associations SET tenant_gid='99'")
    elif change == 'device': batch['device_id'] = 'another-device'
    elif change == 'nonce': event['interaction_id'] = 'b'*64
    elif change == 'auth': case.pins['token'] = 'stolen'
    elif change == 'outcome-id': event['outcome']['request_id'] = 'other'
    elif change == 'busy': event['outcome']['status'] = 'busy'
    elif change == 'extra': event['outcome']['result']['file_path'] = 'secret'
    elif change == 'oversize': batch['events'] *= 257
    batch = seal(batch, signing, prefix=b'wrong-domain\n' if change == 'signature-domain' else b'ai00.viewer.interaction.events.v1\n')
    with pytest.raises((ValueError, RuntimeError)): append(case, batch)


def test_changed_duplicate_rolls_back_entire_batch(audit_case, signing):
    case = audit_case
    append(case, seal(case.batch, signing))
    changed = deepcopy(case.batch)
    new = deepcopy(changed['events'][0])
    new.update(request_id='request-2', sequence=2)
    new['outcome']['request_id'] = 'request-2'
    changed['events'][0]['outcome']['status'] = 'outcome_unknown'
    changed['events'].insert(0, new)
    with pytest.raises(ValueError, match='interaction_audit_conflict'):
        append(case, seal(changed, signing))
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT request_id FROM workmanship_sim_viewer_interaction_events')
        assert cur.fetchall() == [dict(request_id='request-1')]


def test_http_receiver_enforces_stream_limit_before_parse(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers import simulation_connector as routes
    assert hasattr(routes, 'viewer_interaction_events'), 'audit HTTP receiver missing'
    app = FastAPI()
    app.include_router(routes.router)
    headers = {'X-AI00-Device-ID':'device-1', 'X-AI00-Runtime-Generation':'1',
        'X-AI00-Runtime-Instance-ID':'runtime-1', 'X-AI00-Runtime-Type':'electron', 'X-AI00-Runtime-Session':'current-token'}
    with TestClient(app) as client:
        response = client.post('/api/v1/simulation/connectors/v2/viewer-interaction/events', content=b' '*(1024*1024+1), headers=headers)
        assert response.status_code == 413
        assert client.post('/api/v1/simulation/connectors/v2/viewer-interaction/events', json={}).status_code == 422


def test_http_receiver_commits_signed_batch_and_returns_exact_ack(audit_case, signing, monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers import simulation_connector as routes
    from plugins.simulation.simulation_backend.data import viewer_interaction_repository as repository
    case = audit_case
    monkeypatch.setattr(repository, 'ViewerInteractionRepository', lambda: case.repository)
    monkeypatch.setattr(routes, 'datetime', SimpleNamespace(now=lambda _: NOW))
    app = FastAPI()
    app.include_router(routes.router)
    headers = {'X-AI00-Device-ID':'device-1', 'X-AI00-Runtime-Generation':'1',
        'X-AI00-Runtime-Instance-ID':'runtime-1', 'X-AI00-Runtime-Type':'electron', 'X-AI00-Runtime-Session':'current-token'}
    with TestClient(app) as client:
        response = client.post('/api/v1/simulation/connectors/v2/viewer-interaction/events', json=seal(case.batch, signing), headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == {'success':True, 'data':{'acknowledged_request_ids':['request-1']}}
        response = client.post('/api/v1/simulation/connectors/v2/viewer-interaction/events', json=seal(case.batch, signing),
            headers={**headers, 'X-AI00-Runtime-Session':'invalid-token'})
        assert response.status_code == 401
