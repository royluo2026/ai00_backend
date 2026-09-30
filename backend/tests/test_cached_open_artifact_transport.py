import pytest
from backend.routers.simulation_connector import _plan_artifact
from plugins.simulation.simulation_backend.application.cache_open_evidence import CACHE_OPEN_CONTRACT_HASH, cache_package_hash
from plugins.simulation.simulation_backend.data.connector_repository import ConnectorRepositoryError


def plan():
    artifact = dict(artifact_id='assembly', media_type='application/vnd.siemens.plmxml+xml', sha256='a'*64, byte_size=12, version=1)
    child = dict(artifact, artifact_id='part', media_type='model/jt')
    package = dict(artifact_ref=artifact, package_dependencies=[dict(package_path='dependencies/part.jt', artifact_ref=child)],
                   cache_binding=dict(batch_id='a'*32, generation=None, snapshot_hash=None, schema_version=1))
    payload = dict(package, package_hash=cache_package_hash(package))
    return {'steps': [dict(operation_id='vismockup.model.open@2', contract_hash=CACHE_OPEN_CONTRACT_HASH, payload=payload)]}


def test_cache_plan_transport_grants_only_exact_top_and_dependency_refs():
    value = plan()
    assert _plan_artifact(value, 'assembly') == value['steps'][0]['payload']['artifact_ref']
    assert _plan_artifact(value, 'part') == value['steps'][0]['payload']['package_dependencies'][0]['artifact_ref']
    assert _plan_artifact(value, 'unrelated') is None


@pytest.mark.parametrize('change', ['contract', 'package_hash', 'local_path', 'dependency_path', 'dependency_ref'])
def test_cache_transport_rejects_changed_or_unclosed_open_contract(change):
    value=plan();step=value['steps'][0];payload=step['payload']
    if change=='contract': step['contract_hash']='sha256:'+'0'*64
    elif change=='package_hash': payload['package_hash']='sha256:'+'0'*64
    elif change=='local_path': payload['local_artifact_path']='C:/injected.plmxml'
    elif change=='dependency_path': payload['package_dependencies'][0]['package_path']='../escape.jt'
    else: payload['package_dependencies'][0]['artifact_ref']['sha256']='b'*64
    with pytest.raises(ConnectorRepositoryError, match='cache_open_artifact_plan_invalid'):
        _plan_artifact(value,'assembly')


def test_legacy_plan_artifact_discovery_unchanged():
    value=plan();value['steps'][0]['operation_id']='vismockup.model.open@1'
    value['steps'][0]['payload']={'artifact_ref':{'artifact_id':'legacy'}}
    assert _plan_artifact(value,'legacy')=={'artifact_id':'legacy'}
