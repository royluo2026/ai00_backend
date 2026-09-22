from copy import deepcopy
import hashlib

import pytest

from backend.contracts.connector_execution_plan_v2 import canonicalize_v2, compute_plan_hash
from backend.tests.test_simulation_connector_runtime_v2_sql import sign_outcome
from plugins.simulation.tests.test_teamcenter_launch_evidence import evidence, NOW, SOURCE_HASH
from plugins.simulation.simulation_backend.application import teamcenter_launch_evidence as module


def seal(row):
    plan, outcome = row['plan_json'], row['outcome_json']
    plan['plan_hash'] = compute_plan_hash(plan)
    row['plan_hash'] = outcome['plan_hash'] = plan['plan_hash']
    outcome['steps'][0]['result_hash'] = 'sha256:' + hashlib.sha256(canonicalize_v2(outcome['steps'][0]['result'])).hexdigest()
    outcome['signature'] = sign_outcome(outcome)
    row['outcome_hash'] = hashlib.sha256(canonicalize_v2(outcome)).hexdigest()


def opened_evidence():
    row, runtime = evidence()
    plan, outcome = row['plan_json'], row['outcome_json']
    plan['major_version'] = 2
    plan['steps'][0].update(operation_id='teamcenter.visualization.launch@2',
        contract_hash='sha256:807ebf90b7f92d994a1da3963c459191750fb21ca8890a096e3bb04d398e407a')
    identity = dict(process_id=123, process_started_utc_ticks='456', document_handle='opened-document')
    identity['document_session'] = 'sha256:' + hashlib.sha256(canonicalize_v2(identity)).hexdigest()
    outcome['steps'][0]['result'] = dict(protocol='ai00.viewer.opened-source.v1',
        launch=deepcopy(outcome['steps'][0]['result']), document_identity=identity)
    seal(row)
    return row, runtime


def verify(row, runtime):
    assert hasattr(module, 'verify_teamcenter_opened_source_evidence'), 'current-open receipt verifier missing'
    return module.verify_teamcenter_opened_source_evidence(row, runtime, actor_id='user-001', tenant_id='tenant-001', now=NOW)


def test_single_signed_receipt_attests_source_and_returned_document():
    row, runtime = opened_evidence()
    value = verify(row, runtime)
    assert value['source_identity_hash'] == SOURCE_HASH
    assert value['document_session'] == row['outcome_json']['steps'][0]['result']['document_identity']['document_session']
    assert value['runtime_instance_id'] == runtime['current_runtime_instance_id']
    assert value['runtime_generation'] == runtime['runtime_generation']


@pytest.mark.parametrize('change', ['legacy', 'wrong-handle', 'signature', 'runtime', 'source', 'extra'])
def test_open_receipt_cannot_be_replaced_by_separate_or_changed_identity(change):
    row, runtime = opened_evidence()
    result = row['outcome_json']['steps'][0]['result']
    if change == 'legacy':
        row, runtime = evidence()
    elif change == 'wrong-handle':
        result['document_identity']['document_handle'] = 'another-document'
        seal(row)  # Even an authentic but internally inconsistent receipt is invalid.
    elif change == 'signature':
        result['document_identity']['document_session'] = 'sha256:' + '0'*64
    elif change == 'runtime':
        runtime['current_runtime_instance_id'] = 'new-process'
    elif change == 'source':
        result['launch']['source_identity_hash'] = 'sha256:'+'0'*64
        seal(row)
    else:
        result['document_identity']['source_association_id'] = 'caller-controlled'
        seal(row)
    with pytest.raises(ValueError):
        verify(row, runtime)
