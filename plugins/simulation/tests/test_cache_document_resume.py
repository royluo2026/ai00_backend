"""A previously opened frozen package regains authority without reopening it."""
import hashlib
import json
import sqlite3
from datetime import timedelta

import pytest

from backend.capability_v2.business_definition import business_definition_hash
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
from backend.contracts.viewer_interaction_v1 import SignedGrant
from plugins.simulation.simulation_backend.application.cache_open_evidence import (
    cache_package_hash, validated_cache_package_revision)
from plugins.simulation.tests.test_cache_open_completion import cache_completion, complete
from plugins.simulation.tests.test_live_document_identity_evidence import evidence as identity_evidence
from plugins.simulation.tests.test_teamcenter_opened_source_evidence import seal
from plugins.simulation.tests.test_teamcenter_launch_evidence import NOW
from plugins.simulation.tests.test_viewer_open_completion import database, opened, signing, completion
from plugins.simulation.tests.test_viewer_interaction_provider import registry

KEY = ('simulation.environment.cache_source.live_document.resume', 1)


def test_resume_cache_rejects_inconsistent_nested_package_hash():
    binding = dict(batch_id='a'*32, generation='b'*32, snapshot_hash=None, schema_version=1)
    payload = dict(cache_binding=binding, preparation_hash='sha256:'+'c'*64,
        source_selector={}, assembly_xml='<PLMXML/>', tc_dependencies=[])
    expected = cache_package_hash(payload)
    envelope = dict(cache_binding=binding, package_hash=expected,
        tc_open_payload={**payload, 'package_hash':'sha256:'+'f'*64})
    document = dict(artifact_ref_json=envelope, content_sha256=expected[7:])
    with pytest.raises(ValueError, match='interaction_binding_stale'):
        validated_cache_package_revision(document)


@pytest.fixture
def resumed_case(database, cache_completion, opened):
    bound = complete(cache_completion)['binding']
    row, _ = identity_evidence()
    identity = opened['outcome_json']['steps'][0]['result']['document_identity']
    plan, outcome = row['plan_json'], row['outcome_json']
    row.update(plan_id='existing-cache-identity', device_id=opened['device_id'],
        actor_gid='30', tenant_gid='20', runtime_instance_id='new-instance',
        runtime_generation=opened['runtime_generation'])
    plan.update(plan_id=row['plan_id'], capability_id='simulation.vismockup.document.existing_identity.read.request',
        device_id=row['device_id'], actor_id='30', tenant_id='20',
        runtime_instance_id='new-instance', runtime_generation=row['runtime_generation'])
    plan['steps'][0].update(operation_id='vismockup.document.existing_identity.read@1',
        contract_hash='sha256:9aa9528fff83c565d3d005daa1167b41cef2f6d413d485790c6c98c139fc1471',
        payload={'expected_document_session': bound['document_session']},
        payload_hash='sha256:' + hashlib.sha256(canonicalize_v2(
            {'expected_document_session': bound['document_session']})).hexdigest())
    outcome.update(plan_id=row['plan_id'], tenant_id='20', runtime_instance_id='new-instance',
        runtime_generation=row['runtime_generation'])
    outcome['steps'][0]['result'] = identity
    stamp = lambda value: value.strftime('%Y-%m-%dT%H:%M:%SZ')
    plan.update(issued_at=stamp(NOW-timedelta(seconds=5)), expires_at=stamp(NOW+timedelta(minutes=5)))
    outcome.update(reported_at=stamp(NOW-timedelta(seconds=1)))
    outcome['steps'][0].update(started_at=stamp(NOW-timedelta(seconds=3)),
        completed_at=stamp(NOW-timedelta(seconds=2)))
    row.update(updated_at=NOW, lease_until=NOW+timedelta(seconds=60))
    seal(row)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='new-instance'")
        columns = list(row)
        db.execute('INSERT INTO workmanship_sim_connector_runtime_plans ('+','.join(columns)+') VALUES ('+
            ','.join('?' for _ in columns)+')',
            [json.dumps(row[key]) if isinstance(row[key], dict) else row[key].isoformat()
             if hasattr(row[key], 'isoformat') else row[key] for key in columns])
    return cache_completion, bound


def resume(case, **changes):
    completion, bound = case
    descriptor = registry().get(KEY, (None, None, None))[2]
    context = completion.context if descriptor is None else completion.context.model_copy(update={
        'capability_version_gid': descriptor.capability_version_gid,
        'business_definition_hash': business_definition_hash(descriptor)})
    payload = dict(workspace_gid='10', document_gid='11',
        identity_operation_id='existing-cache-identity',
        expected_document_session=bound['document_session'],
        expected_workspace_row_version=bound['workspace_row_version'],
        idempotency_key='resume-cache-1', session_nonce='b'*64)
    return completion.provider.resume_cache({**payload, **changes}, context).data


@pytest.mark.parametrize('role', ['primary', 'inserted'])
def test_resume_cache_replays_one_signed_grant_without_open(database, resumed_case, role):
    with sqlite3.connect(database) as db:
        db.execute('UPDATE workmanship_sim_vm_documents SET document_role=?', (role,))
        before = [db.execute('SELECT COUNT(*) FROM workmanship_sim_'+table).fetchone()[0]
                  for table in ('connector_runtime_plans', 'vm_documents')]
    result = resume(resumed_case)
    assert SignedGrant.model_validate(result['grant']).verify_signature(resumed_case[0].public)
    assert result['grant']['session_nonce'] == 'b'*64
    assert result['binding']['document_session'] == resumed_case[1]['document_session']
    assert result['binding']['workspace_row_version'] == resumed_case[1]['workspace_row_version']
    assert resume(resumed_case) == result
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT row_version FROM workmanship_sim_workspaces').fetchone()[0] == result['binding']['workspace_row_version']
        assert [db.execute('SELECT COUNT(*) FROM workmanship_sim_'+table).fetchone()[0]
                for table in ('connector_runtime_plans', 'vm_documents')] == before
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_source_associations WHERE active=1').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_interaction_grants').fetchone()[0] == 2


@pytest.mark.parametrize('change', ['batch', 'package', 'content', 'association', 'device',
    'session', 'runtime_instance', 'runtime_generation', 'version', 'owner'])
def test_resume_cache_rejects_changed_pins(database, resumed_case, change):
    sql = {
        'content': "UPDATE workmanship_sim_vm_documents SET content_sha256='0'",
        'association': "UPDATE workmanship_sim_viewer_source_associations SET source_revision='0'",
        'device': "UPDATE workmanship_sim_vm_documents SET connector_device_id='other'",
        'session': "UPDATE workmanship_sim_live_document_bindings SET document_session='different'",
        'runtime_instance': "UPDATE workmanship_sim_connector_runtime_devices SET current_runtime_instance_id='other'",
        'runtime_generation': 'UPDATE workmanship_sim_connector_runtime_devices SET runtime_generation=99',
        'version': 'UPDATE workmanship_sim_workspaces SET row_version=row_version+1',
        'owner': "UPDATE workmanship_sim_vm_documents SET owner_gid='99'",
    }.get(change)
    with sqlite3.connect(database) as db:
        if change in {'batch', 'package'}:
            envelope = json.loads(db.execute('SELECT artifact_ref_json FROM workmanship_sim_vm_documents').fetchone()[0])
            if change == 'batch': envelope['cache_binding']['batch_id'] = 'f'*32
            else: envelope['package_hash'] = 'sha256:'+'f'*64
            db.execute('UPDATE workmanship_sim_vm_documents SET artifact_ref_json=?', (json.dumps(envelope),))
        else: db.execute(sql)
    with pytest.raises(CapabilityBusinessError): resume(resumed_case)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_interaction_grants').fetchone()[0] == 1


def test_resume_cache_nonce_conflict(database, resumed_case):
    resume(resumed_case)
    with pytest.raises(CapabilityBusinessError, match='idempotency_conflict'):
        resume(resumed_case, session_nonce='c'*64)


@pytest.mark.parametrize('failure', ['signer', 'proof'])
def test_resume_cache_rolls_back_signer_and_proof_failures(database, resumed_case, failure):
    if failure == 'signer': resumed_case[0].record['revoked'] = True
    else:
        with sqlite3.connect(database) as db:
            db.execute("CREATE TRIGGER fail_resume_proof BEFORE INSERT ON workmanship_sim_viewer_grant_evidence BEGIN SELECT RAISE(ABORT,'proof failure'); END")
    with pytest.raises((CapabilityBusinessError, sqlite3.IntegrityError)): resume(resumed_case)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_interaction_grants').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM workmanship_sim_viewer_source_associations').fetchone()[0] == 1


def test_resume_cache_rejects_stale_identity(database, resumed_case):
    with sqlite3.connect(database) as db:
        db.execute("UPDATE workmanship_sim_connector_runtime_plans SET updated_at=? WHERE plan_id='existing-cache-identity'",
                   ((NOW-timedelta(minutes=3)).isoformat(),))
    with pytest.raises(CapabilityBusinessError): resume(resumed_case)
