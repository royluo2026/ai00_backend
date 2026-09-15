from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.contracts.connector_execution_plan_v2 import canonicalize_v2, compute_plan_hash
from backend.tests.test_simulation_connector_runtime_v2_sql import sign_outcome
from plugins.simulation.simulation_backend.application.live_document_identity import verify_identity_evidence

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 7, 1, 3, tzinfo=UTC)
CONTRACT_HASH = 'sha256:2a8b6e89d3a13cf35b0584a989ed79977700d3cd3fe9fcc918c3b871d1c8c4d7'


def evidence():
    vector = json.loads((ROOT / 'backend/tests/fixtures/connector_execution_plan_v2.json').read_text())
    plan, outcome = vector['plan'], vector['outcome']
    plan.update(capability_id='simulation.vismockup.document.identity.read.request', major_version=1)
    plan['steps'][0].update(operation_id='vismockup.document.identity.read@1', contract_hash=CONTRACT_HASH,
                           payload={}, payload_hash='sha256:' + hashlib.sha256(canonicalize_v2({})).hexdigest())
    plan['plan_hash'] = compute_plan_hash(plan)
    identity = dict(process_id=123, process_started_utc_ticks='638900000000000001', document_handle='42')
    identity['document_session'] = 'sha256:' + hashlib.sha256(canonicalize_v2(identity)).hexdigest()
    outcome.update(plan_hash=plan['plan_hash'], reported_at='2026-09-07T01:02:59Z')
    outcome['steps'][0].update(result=identity, result_hash='sha256:' + hashlib.sha256(canonicalize_v2(identity)).hexdigest(),
                              started_at='2026-09-07T01:02:57Z', completed_at='2026-09-07T01:02:58Z')
    outcome['signature'] = sign_outcome(outcome)
    row = dict(plan_id=plan['plan_id'], device_id=plan['device_id'], tenant_gid=plan['tenant_id'],
        actor_gid=plan['actor_id'], protocol=plan['protocol'], runtime_generation=plan['runtime_generation'],
        runtime_instance_id=plan['runtime_instance_id'], session_token_hash='session-hash', lease_id=outcome['lease_id'],
        plan_hash=plan['plan_hash'], plan_json=plan, outcome_json=outcome, status='succeeded',
        outcome_hash=hashlib.sha256(canonicalize_v2(outcome)).hexdigest(), updated_at=NOW,
        lease_until=NOW + timedelta(seconds=60))
    runtime = dict(device_id=plan['device_id'], owner_user_gid=plan['actor_id'], tenant_gid=plan['tenant_id'],
        protocol=plan['protocol'], runtime_type='electron', status='active', runtime_generation=plan['runtime_generation'],
        current_runtime_instance_id=plan['runtime_instance_id'], session_token_hash='session-hash',
        session_expires_at=NOW + timedelta(minutes=5), heartbeat_at=NOW,
        device_key_id=outcome['device_key_id'], device_signing_jwk=vector['device_public_jwk'])
    return row, runtime


def verify(row, runtime, now=NOW):
    return verify_identity_evidence(row, runtime, actor_id='user-001', tenant_id='tenant-001', now=now)


def test_verifies_only_persisted_signed_identity():
    row, runtime = evidence()
    assert verify(row, runtime) == dict(connector_device_id='device-001',
        document_session=row['outcome_json']['steps'][0]['result']['document_session'])


def test_native_contract_pin_matches_canonical_descriptor():
    descriptor = json.loads((ROOT/'docs/contracts/vismockup.document.identity.read@1.json').read_text())
    digest = 'sha256:' + hashlib.sha256(json.dumps(descriptor,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
    assert DIRECT_VISMOCKUP_OPERATIONS['identity'] == ('vismockup.document.identity.read@1',digest)
    assert digest == CONTRACT_HASH


@pytest.mark.parametrize('target,field,value', [
    ('row','actor_gid','other'), ('row','tenant_gid','other'), ('row','device_id','other'),
    ('row','plan_hash','0'*64), ('row','outcome_hash','0'*64), ('row','runtime_generation',8),
    ('row','runtime_instance_id','other'), ('row','session_token_hash','other'), ('row','lease_id','other'),
    ('row','status','failed_without_effect'), ('runtime','owner_user_gid','other'), ('runtime','tenant_gid','other'),
    ('runtime','runtime_generation',8), ('runtime','current_runtime_instance_id','other'),
    ('runtime','runtime_type','legacy'), ('runtime','status','revoked'),
    ('runtime','session_expires_at',NOW), ('row','updated_at',NOW-timedelta(minutes=3)),
    ('row','updated_at',NOW+timedelta(seconds=1)),
])
def test_refuses_identity_scope_lease_and_receipt_mismatch(target, field, value):
    row, runtime = evidence()
    (row if target == 'row' else runtime)[field] = value
    with pytest.raises(ValueError):
        verify(row, runtime)


@pytest.mark.parametrize('change', ['forged','signature','session','extra_result','hash','operation','stale','future','failed'])
def test_refuses_forged_wrong_contract_and_bad_signed_result(change):
    row, runtime = evidence()
    outcome = row['outcome_json']
    result = outcome['steps'][0]['result']
    if change == 'signature':
        outcome['signature'] = ('A' if outcome['signature'][0] != 'A' else 'B') + outcome['signature'][1:]
        row['outcome_hash'] = hashlib.sha256(canonicalize_v2(outcome)).hexdigest()
    if change in {'forged','session'}: result['document_session'] = 'sha256:' + '0'*64
    if change == 'extra_result': result['path'] = 'not allowed'
    if change == 'hash': row['plan_json']['steps'][0]['contract_hash'] = 'sha256:' + '0'*64
    if change == 'operation': row['plan_json']['steps'][0]['operation_id'] = 'vismockup.tree.read@2'
    if change == 'stale': outcome['steps'][0]['completed_at'] = '2026-09-07T00:59:58Z'
    if change == 'future': outcome['steps'][0]['completed_at'] = '2026-09-07T01:03:01Z'
    if change == 'failed': outcome['overall_status'] = 'failed_without_effect'
    if change not in {'forged','signature'}:
        outcome['steps'][0]['result_hash'] = 'sha256:' + hashlib.sha256(canonicalize_v2(result)).hexdigest()
        row['plan_json']['plan_hash'] = compute_plan_hash(row['plan_json'])
        row['plan_hash'] = outcome['plan_hash'] = row['plan_json']['plan_hash']
        outcome['signature'] = sign_outcome(outcome)
        row['outcome_hash'] = hashlib.sha256(canonicalize_v2(outcome)).hexdigest()
    with pytest.raises(ValueError): verify(row, runtime)
