from types import SimpleNamespace

import json
import jsonschema
import pytest

from backend.tests.test_viewer_interaction_repository import grant_case, request
from plugins.simulation.tests.test_viewer_interaction_authorization import signing, NOW
from plugins.simulation.simulation_backend.capabilities.connector_runtime import (
    ConnectorControlPlane, register_connector_runtime_capabilities,
)


class Registry:
    def __init__(self): self.items = {}
    def register(self, spec, handler, *, descriptor):
        self.items[spec.id, spec.version] = (spec, handler, descriptor)


def registry():
    value = Registry()
    register_connector_runtime_capabilities(value, ConnectorControlPlane(SimpleNamespace()))
    return value.items


def test_new_interaction_and_launch_bind_versions_are_registered_without_replacing_v1():
    items = registry()
    for key in [('simulation.viewer.interaction.scope.get', 1),
                ('simulation.viewer.interaction.authorize', 1),
                ('simulation.environment.online_source.live_document.bind', 2),
                ('simulation.teamcenter.visualization.launch.request', 2),
                ('simulation.teamcenter.visualization.launch', 2)]:
        assert key in items, key
    assert ('simulation.environment.online_source.live_document.bind', 1) in items
    assert ('simulation.teamcenter.visualization.launch.request', 1) in items
    for name in ('scope.get', 'authorize'):
        descriptor = items['simulation.viewer.interaction.' + name, 1][2]
        assert descriptor.exposure.web and not descriptor.exposure.agent
        assert not descriptor.exposure.api and not descriptor.exposure.local_runtime


def test_scope_get_resolves_authoritative_association_and_authorize_returns_signed_grant(grant_case, signing):
    from plugins.simulation.simulation_backend.capabilities import viewer_interaction
    provider = viewer_interaction.ViewerInteractionProvider(grant_case.repository, signing[0], clock=lambda: NOW)
    scope = provider.scope_get(dict(workspace_gid='10', document_gid='20'), grant_case.context).data
    assert scope == dict(source_association_id=grant_case.association)
    grant = provider.authorize(request(grant_case), grant_case.context).data
    assert grant['source_association_id'] == scope['source_association_id']
    assert grant['grant_generation'] == 1
    for suffix, data in [('scope.get', scope), ('authorize', grant)]:
        jsonschema.validate(data, registry()['simulation.viewer.interaction.' + suffix, 1][0].output_schema)


@pytest.mark.parametrize('owned,expected', [(True, 'interaction_source_unassociated'), (False, 'interaction_scope_denied')])
def test_scope_get_only_exposes_unassociated_code_for_owned_online_document(grant_case, owned, expected):
    from plugins.simulation.simulation_backend.capabilities.viewer_interaction import ViewerInteractionProvider
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    with grant_case.connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_vm_documents SET document_role='inserted'")
        cur.execute('UPDATE workmanship_sim_viewer_source_associations SET active=0')
        if not owned:
            cur.execute("UPDATE workmanship_sim_vm_documents SET owner_gid='99'")
    provider = ViewerInteractionProvider(grant_case.repository, None, clock=lambda: NOW)
    with pytest.raises(CapabilityBusinessError) as raised:
        provider.scope_get(dict(workspace_gid='10', document_gid='20'), grant_case.context)
    assert raised.value.code == expected


@pytest.mark.parametrize('payload', [dict(workspace_gid='10', document_gid='21'),
    dict(workspace_gid='10', document_gid='20', source_association_id='injected')])
def test_scope_get_rejects_unbound_document_and_caller_pins(grant_case, signing, payload):
    from plugins.simulation.simulation_backend.capabilities import viewer_interaction
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    provider = viewer_interaction.ViewerInteractionProvider(grant_case.repository, signing[0], clock=lambda: NOW)
    with pytest.raises(CapabilityBusinessError):
        provider.scope_get(payload, grant_case.context)


def test_launch_v2_plan_uses_current_open_operation_and_distinct_identity():
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import _direct_vismockup_plan_v2
    context = CapabilityContext(user_gid='11', team_gid='12', request_id='launch-request',
        catalog_release='rel_' + 'a'*32, normalized_input_hash='sha256:' + 'b'*64,
        capability_version_gid='cv2_' + 'c'*24, business_definition_hash='sha256:' + 'd'*64)
    args = dict(action='tc_launch', connector_id='device-1', payload={}, context=context, now=NOW)
    first = _direct_vismockup_plan_v2(**args)
    second = _direct_vismockup_plan_v2(**args, major_version=2)
    assert second['major_version'] == 2
    assert second['steps'][0]['operation_id'] == 'teamcenter.visualization.launch@2'
    assert second['steps'][0]['contract_hash'] == 'sha256:807ebf90b7f92d994a1da3963c459191750fb21ca8890a096e3bb04d398e407a'
    assert first['steps'][0]['operation_id'] == 'teamcenter.visualization.launch@1'
    assert first['plan_id'] != second['plan_id']


def test_registered_launch_v2_handler_queues_major2_receipt_without_identity_read():
    from backend.capability_v2.provider_contracts import CapabilityContext
    from backend.capability_v2.contracts import OperationRef, OperationStatus
    queued = []
    runtime = dict(device_id='device-1', runtime_type='electron')
    class Control:
        repository = SimpleNamespace(bound_runtime_for_user=lambda *_: runtime)
        clock = staticmethod(lambda: NOW)
        plan_signer = None
        def queue_v2(self, plan, context, *, runtime_row):
            assert runtime_row is runtime
            queued.append(plan)
            return OperationRef(operation_id=plan['plan_id'], status=OperationStatus.ACCEPTED)
    value = Registry()
    register_connector_runtime_capabilities(value, Control())
    handler = value.items['simulation.teamcenter.visualization.launch.request', 2][1]
    payload = dict(source_selector=dict(endpoint_id='tc-production', object_uid='source', item_revision_uid='rev',
        bom_view_uid='', revision_rule='Latest Working', configuration_date='2026-09-22T00:00:00Z'), expected_visdoc_uid='')
    result = handler(payload, CapabilityContext(user_gid='11', team_gid='12', source='web', request_id='open-2',
        catalog_release='rel_'+'a'*32, normalized_input_hash='sha256:'+'b'*64, confirmation_token='confirm-open'))
    assert result.data['operation_id'] == queued[0]['plan_id']
    assert queued[0]['major_version'] == 2
    assert len(queued[0]['steps']) == 1
    assert queued[0]['steps'][0]['operation_id'] == 'teamcenter.visualization.launch@2'
    assert queued[0]['steps'][0]['payload'] == payload


def test_launch_v2_preserves_explicit_confirmation_requirement_for_new_runtime():
    from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2
    from plugins.simulation.tests.test_teamcenter_opened_source_evidence import opened_evidence
    from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository
    row, _ = opened_evidence()
    plan = ConnectorExecutionPlanV2.model_validate(row['plan_json'])
    prior = plan.model_dump(mode='json')
    repeated = plan.model_copy(update={'confirmation_receipt_id':'fresh-explicit-confirmation'})
    assert SimulationConnectorRepository._repeat_is_freshly_confirmed_document_launch(repeated, prior)
    assert not SimulationConnectorRepository._repeat_is_freshly_confirmed_document_launch(plan, prior)
    assert not SimulationConnectorRepository._repeat_is_freshly_confirmed_document_launch(
        plan.model_copy(update={'confirmation_receipt_id':None}), prior)


def test_cache_bound_launch_resolves_server_identity_and_queues_one_native_launch(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityContext
    from backend.capability_v2.contracts import OperationRef, OperationStatus
    queued=[];runtime=dict(device_id='device-1',runtime_type='electron')
    class Control:
        repository=SimpleNamespace(bound_runtime_for_user=lambda *_:runtime)
        clock=staticmethod(lambda:NOW);plan_signer=None
        def queue_v2(self,plan,context,*,runtime_row):
            queued.append(plan);return OperationRef(operation_id=plan['plan_id'],status=OperationStatus.ACCEPTED)
    monkeypatch.setattr(
        'plugins.simulation.simulation_backend.capabilities.connector_runtime._resolve_cache_visualization_source',
        lambda source,context:dict(endpoint_id='tc-production',object_uid='rev-node',item_revision_uid='rev-node',
            bom_view_uid='',revision_rule='Latest Working',configuration_date='2026-09-22T00:00:00Z'))
    value=Registry();register_connector_runtime_capabilities(value,Control())
    handler=value.items['simulation.teamcenter.visualization.launch.request',3][1]
    payload={'cache_source':{'batch_id':'a'*32,'node_key':'sha256:'+'b'*64},'expected_visdoc_uid':''}
    result=handler(payload,CapabilityContext(user_gid='11',team_gid='12',source='web',request_id='cache-open',
        catalog_release='rel_'+'a'*32,normalized_input_hash='sha256:'+'b'*64,confirmation_token='confirm-open'))
    assert result.data['operation_id']==queued[0]['plan_id']
    assert queued[0]['major_version']==3
    assert len(queued[0]['steps'])==1
    assert queued[0]['steps'][0]['operation_id']=='teamcenter.visualization.launch@2'
    assert queued[0]['steps'][0]['payload']=={
        'source_selector':{'endpoint_id':'tc-production','object_uid':'rev-node','item_revision_uid':'rev-node',
            'bom_view_uid':'','revision_rule':'Latest Working','configuration_date':'2026-09-22T00:00:00Z'},
        'expected_visdoc_uid':''}
    assert all(token not in json.dumps(queued[0]).lower() for token in ('file.fetch','artifact.upload','ois'))


def test_cache_bound_insert_reuses_single_existing_insert_operation(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityContext
    from backend.capability_v2.contracts import OperationRef, OperationStatus
    queued=[];runtime=dict(device_id='device-1',runtime_type='electron')
    class Control:
        repository=SimpleNamespace(bound_runtime_for_user=lambda *_:runtime)
        clock=staticmethod(lambda:NOW);plan_signer=None
        def queue_v2(self,plan,context,*,runtime_row):
            queued.append(plan);return OperationRef(operation_id=plan['plan_id'],status=OperationStatus.ACCEPTED)
    monkeypatch.setattr(
        'plugins.simulation.simulation_backend.capabilities.connector_runtime._resolve_cache_visualization_source',
        lambda *_:dict(endpoint_id='tc-production',object_uid='rev-node',item_revision_uid='rev-node',bom_view_uid='',
            revision_rule='Latest Working',configuration_date='2026-09-22T00:00:00Z'))
    value=Registry();register_connector_runtime_capabilities(value,Control())
    handler=value.items['simulation.teamcenter.visualization.insert.request',2][1]
    handler({'cache_source':{'batch_id':'a'*32,'node_key':'node'},'expected_visdoc_uid':''},CapabilityContext(
        user_gid='11',team_gid='12',source='web',request_id='cache-insert',catalog_release='rel_'+'a'*32,
        normalized_input_hash='sha256:'+'b'*64,confirmation_token='confirm-insert'))
    assert queued[0]['major_version']==2
    assert len(queued)==1 and len(queued[0]['steps'])==1
    assert queued[0]['steps'][0]['operation_id']=='teamcenter.visualization.insert@1'


@pytest.mark.parametrize('version,key',[(3,('simulation.teamcenter.visualization.launch.request',3)),
    (2,('simulation.teamcenter.visualization.insert.request',2))])
def test_cache_bound_visualization_contract_is_closed(version,key):
    spec,_,descriptor=registry()[key]
    assert descriptor.transaction_policy['mode']=='external'
    assert any(resource.resource_type=='simulation-model-cache-node' and not resource.required
        for resource in descriptor.resource_selectors)
    good={'cache_source':{'batch_id':'a'*32,'node_key':'node'},'expected_visdoc_uid':''}
    jsonschema.validate(good,spec.input_schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**good,'item_revision_uid':'injected'},spec.input_schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**good,'source_selector':{'endpoint_id':'tc-production'}},spec.input_schema)
