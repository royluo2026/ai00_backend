from copy import deepcopy
from datetime import timedelta
import pytest
from backend.contracts.connector_execution_plan_v1 import canonical_hash
from plugins.simulation.tests.test_teamcenter_opened_source_evidence import opened_evidence, seal
from plugins.simulation.tests.test_teamcenter_launch_evidence import NOW
from plugins.simulation.simulation_backend.application.cache_open_evidence import (
    verify_cache_open_evidence, CACHE_OPEN_CONTRACT_HASH)

BINDING = dict(batch_id='a'*32, generation='b'*32, snapshot_hash='sha256:'+'c'*64, schema_version=1)
ARTIFACT = dict(artifact_id='artifact-cache+模型', media_type='application/vnd.siemens.plmxml+xml', sha256='d'*64, byte_size=42, version=1)

def make_cache(row):
    plan, outcome = row['plan_json'], row['outcome_json']
    package = dict(artifact_ref=deepcopy(ARTIFACT), package_dependencies=[], cache_binding=deepcopy(BINDING))
    payload = dict(**package, package_hash=canonical_hash(package))
    plan.update(capability_id='simulation.environment.cache_source.open.request', major_version=1)
    plan['steps'][0].update(operation_id='vismockup.model.open@2', contract_hash=CACHE_OPEN_CONTRACT_HASH,
        payload=payload, payload_hash=canonical_hash(payload))
    identity = outcome['steps'][0]['result']['document_identity']
    outcome['steps'][0]['result'] = dict(protocol='ai00.viewer.opened-cache.v1', cache_binding=deepcopy(BINDING),
        artifact_ref=deepcopy(ARTIFACT), package_hash=payload['package_hash'], document_identity=identity)
    seal(row)
    return row

def verify(row, runtime):
    return verify_cache_open_evidence(row, runtime, actor_id='user-001', tenant_id='tenant-001', now=NOW)

def test_exact_signed_cache_package_and_document_identity():
    row, runtime = opened_evidence()
    make_cache(row)
    result = verify(row, runtime)
    assert result['artifact_ref'] == ARTIFACT and result['cache_binding'] == BINDING
    assert result['package_hash'] == row['plan_json']['steps'][0]['payload']['package_hash']

@pytest.mark.parametrize('change', ['artifact', 'binding', 'package', 'identity', 'dependency', 'contract',
    'capability', 'signature', 'owner', 'tenant', 'runtime', 'stale'])
def test_cache_receipt_rejects_cross_scope_or_changed_package(change):
    row, runtime = opened_evidence()
    make_cache(row)
    receipt = row['outcome_json']['steps'][0]['result']
    if change == 'artifact': receipt['artifact_ref']['artifact_id'] = 'other'
    elif change == 'binding': receipt['cache_binding']['batch_id'] = 'f'*32
    elif change == 'package': receipt['package_hash'] = 'sha256:'+'0'*64
    elif change == 'identity': receipt['document_identity']['document_handle'] = 'other'
    elif change == 'dependency': row['plan_json']['steps'][0]['payload']['package_dependencies'] = [{'package_path':'dependencies/other.jt','artifact_ref':ARTIFACT}]
    elif change == 'contract': row['plan_json']['steps'][0]['contract_hash'] = 'sha256:'+'f'*64
    elif change == 'capability': row['plan_json']['capability_id'] = 'simulation.teamcenter.visualization.launch.request'
    elif change == 'owner': runtime['owner_user_gid'] = 'other'
    elif change == 'tenant': row['tenant_gid'] = 'other'
    elif change == 'runtime': runtime['runtime_generation'] += 1
    elif change == 'stale': row['updated_at'] = NOW-timedelta(minutes=3)
    elif change == 'signature': receipt['package_hash'] = 'sha256:'+'0'*64
    if change != 'signature': seal(row)
    with pytest.raises(ValueError): verify(row, runtime)

def make_tc_cache(row):
    import json
    from pathlib import Path
    from plugins.simulation.simulation_backend.application.cache_tc_open_contract import TC_OPEN_CONTRACT_HASH
    root=Path(__file__).resolve().parents[3]
    payload=json.loads((root/'local-runtime/tests/Ai00.Connector.Tests/Fixtures/tc-local-open.json').read_text())[0]
    plan,outcome=row['plan_json'],row['outcome_json']
    plan.update(capability_id='simulation.environment.cache_source.open.request',major_version=1)
    plan['steps'][0].update(operation_id='vismockup.model.open@3',contract_hash=TC_OPEN_CONTRACT_HASH,
        payload=payload,payload_hash=canonical_hash(payload))
    identity=outcome['steps'][0]['result']['document_identity']
    outcome['steps'][0]['result']=dict(protocol='ai00.viewer.opened-tc-cache.v1',cache_binding=payload['cache_binding'],
        package_hash=payload['package_hash'],files=[dict(dependency_key=d['file_ref']['dependency_key'],sha256='d'*64,byte_size=32) for d in payload['tc_dependencies']],document_identity=identity)
    seal(row)

def test_tc_local_receipt_binds_exact_files_without_artifacts():
    row,runtime=opened_evidence();make_tc_cache(row)
    result=verify(row,runtime)
    assert result['tc_open_payload']==row['plan_json']['steps'][0]['payload']
    assert 'artifact_ref' not in result

@pytest.mark.parametrize('change',['missing','duplicate','wrong_file','device','generation','instance','binding','identity','bytes','upload'])
def test_tc_local_receipt_rejects_cross_client_or_incomplete_proof(change):
    row,runtime=opened_evidence();make_tc_cache(row)
    receipt=row['outcome_json']['steps'][0]['result']
    if change=='missing':receipt['files']=[]
    elif change=='duplicate':receipt['files']*=2
    elif change=='wrong_file':receipt['files'][0]['dependency_key']='e'*64
    elif change=='device':runtime['device_id']='other-device'
    elif change=='generation':runtime['runtime_generation']+=1
    elif change=='instance':runtime['current_runtime_instance_id']='other-instance'
    elif change=='binding':receipt['cache_binding']={**receipt['cache_binding'],'batch_id':'f'*32}
    elif change=='identity':receipt['document_identity']['document_handle']='other'
    elif change=='bytes':receipt['files'][0]['byte_size']=0
    elif change=='upload':receipt['artifact_ref']=ARTIFACT
    seal(row)
    with pytest.raises(ValueError):verify(row,runtime)
