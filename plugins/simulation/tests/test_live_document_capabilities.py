from types import SimpleNamespace
import pytest
import jsonschema

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.simulation.simulation_backend.capabilities.live_documents import LiveDocumentProvider, BINDING_INPUT
from plugins.simulation.simulation_backend.capabilities.connector_runtime import ConnectorControlPlane, register_connector_runtime_capabilities
from plugins.simulation.simulation_backend.data.connector_repository import ConnectorRepositoryError
from plugins.simulation.tests.test_live_document_binding_repository import database, count
from plugins.simulation.tests.test_live_document_identity_evidence import NOW


class Connectors:
    def __init__(self): self.calls = []; self.fail = False
    def verified_document_identity(self, operation_id, **scope):
        self.calls.append((operation_id, scope))
        if self.fail: raise ConnectorRepositoryError('live_document_identity_unavailable')
        return dict(connector_device_id='device-A', document_session='sha256:'+'a'*64)
    def bound_runtime_for_user(self, actor, tenant):
        from datetime import timedelta
        return dict(device_id='device-A',owner_user_gid=actor,tenant_gid=tenant,runtime_type='electron',status='active',
            protocol='ai00.connector.execution-plan.v2',runtime_generation=7,
            current_runtime_instance_id='instance',session_token_hash='hash',session_expires_at=NOW+timedelta(minutes=2),heartbeat_at=NOW)
    def verified_hierarchy_inventory(self, operation_id, **scope):
        self.calls.append((operation_id, scope))
        return dict(connector_device_id='device-A', document_session='sha256:'+'a'*64,
            start_index=0, next_index=None, total_hierarchies=0, hierarchies=[])


def context(): return CapabilityContext(user_gid='30',team_gid='20',source='web')
def request(): return dict(identity_operation_id='identity-op',name='Live document',
    document_display_name='W10-ENG00001/00;1-工程分支(Top Engineering) (视图)',idempotency_key='same-key')


def test_adoption_uses_trusted_identity_and_duplicate_is_durable(database):
    connectors = Connectors()
    provider = LiveDocumentProvider(connectors, clock=lambda: NOW)
    first = provider.adopt(request(), context()).data
    assert first['state'] == 'importing'
    assert first['model_document_gid']
    assert provider.adopt(request(), context()).data == first
    assert count(database,'workspaces') == 1
    assert connectors.calls[0] == ('identity-op',dict(actor_id='30',tenant_id='20',now=NOW))
    native = provider.binding({'identity_operation_id':'identity-op'},context()).data
    selected = provider.binding({'workspace_gid':first['workspace_gid']},context()).data
    assert native == selected
    assert native['document_session'] == 'sha256:'+'a'*64


def test_rebind_uses_fresh_signed_identity_for_the_owned_workspace(database):
    connectors = Connectors()
    provider = LiveDocumentProvider(connectors, clock=lambda: NOW)
    created = provider.adopt(request(), context()).data
    connectors.verified_document_identity = lambda operation_id, **scope: dict(
        connector_device_id='device-A', document_session='sha256:'+'b'*64)

    result = provider.rebind({
        'workspace_gid': created['workspace_gid'],
        'identity_operation_id': 'new-identity-op',
        'expected_document_session': 'sha256:'+'a'*64,
        'expected_workspace_row_version': 2,
        'idempotency_key': 'rebind-key',
    }, context()).data

    assert result['document_session'] == 'sha256:'+'b'*64
    assert provider.binding({'identity_operation_id':'new-identity-op'}, context()).data['workspace_gid'] == created['workspace_gid']


def test_rebind_never_accepts_a_raw_or_other_owner_identity(database):
    connectors = Connectors()
    provider = LiveDocumentProvider(connectors, clock=lambda: NOW)
    created = provider.adopt(request(), context()).data
    payload = {'workspace_gid': created['workspace_gid'], 'identity_operation_id':'new-identity-op',
        'expected_document_session':'sha256:'+'a'*64, 'expected_workspace_row_version':2,
        'idempotency_key':'rebind-key'}
    with pytest.raises(CapabilityBusinessError):
        provider.rebind({**payload, 'document_session':'raw'}, context())
    with pytest.raises(CapabilityBusinessError, match='workspace_not_found'):
        provider.rebind(payload, context().model_copy(update={'user_gid':'31'}))


def test_refused_evidence_and_raw_ui_session_never_create(database):
    connectors = Connectors(); connectors.fail = True
    provider = LiveDocumentProvider(connectors,clock=lambda: NOW)
    with pytest.raises(CapabilityBusinessError): provider.adopt(request(),context())
    assert provider.binding({'identity_operation_id':'forged'},context()).data == dict(
        state='unavailable',workspace_gid=None,version_gid=None,connector_device_id=None,document_session=None)
    with pytest.raises(CapabilityBusinessError): provider.adopt({**request(),'document_session':'forged'},context())
    with pytest.raises(CapabilityBusinessError): provider.adopt(request(),context().model_copy(update={'source':'agent'}))
    assert count(database,'workspaces') == 0


def test_binding_unbound_does_not_leak_other_owner(database):
    provider = LiveDocumentProvider(Connectors(),clock=lambda: NOW)
    assert provider.binding({'identity_operation_id':'identity-op'},context()).data['state'] == 'unbound'
    workspace = provider.adopt(request(),context()).data['workspace_gid']
    result = provider.binding({'workspace_gid':workspace},context().model_copy(update={'user_gid':'31'})).data
    assert result == dict(state='unbound',workspace_gid=None,version_gid=None,connector_device_id=None,document_session=None)


def test_binding_runtime_loss_is_unavailable_without_saved_identity_disclosure(database):
    connectors = Connectors(); provider = LiveDocumentProvider(connectors,clock=lambda: NOW)
    workspace = provider.adopt(request(),context()).data['workspace_gid']
    connectors.bound_runtime_for_user = lambda *_: None
    assert provider.binding({'workspace_gid':workspace},context()).data == dict(
        state='unavailable',workspace_gid=None,version_gid=None,connector_device_id=None,document_session=None)


@pytest.mark.parametrize('payload',[{}, {'workspace_gid':'1','identity_operation_id':'x'}, {'document_session':'raw'}])
def test_binding_selector_is_closed_and_exclusive(payload):
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(payload,BINDING_INPUT)


class Registry:
    def __init__(self): self.items = {}
    def register(self,spec,handler,*,descriptor): self.items[spec.id] = (spec,handler,descriptor)


def test_identity_read_is_empty_read_only_app_plan_and_candidate_web_only():
    from backend.capability_v2.contracts import OperationRef, OperationStatus
    connectors = Connectors(); control = ConnectorControlPlane(connectors,clock=lambda: NOW)
    queued = []
    control.queue_v2 = lambda plan,ctx,**kw: queued.append(plan) or OperationRef(operation_id=plan['plan_id'],status=OperationStatus.ACCEPTED)
    registry = Registry(); register_connector_runtime_capabilities(registry,control)
    ctx = context().model_copy(update=dict(capability_version_gid='cv2_'+'a'*24,business_definition_hash='sha256:'+'b'*64,
        catalog_release='rel_test',request_id='request',idempotency_key='key',normalized_input_hash='sha256:'+'c'*64))
    spec,handler,descriptor = registry.items['simulation.vismockup.document.identity.read.request']
    handler({},ctx)
    step = queued[0]['steps'][0]
    assert step['payload'] == {}
    assert step['side_effect_classification'] == 'read'
    assert step['post_condition_probe_id'] is None
    assert step['operation_id'] == 'vismockup.document.identity.read@1'
    for name in ('simulation.vismockup.document.identity.read.request','simulation.vismockup.document.hierarchy_inventory.read.request',
                 'simulation.environment.live_document.adopt','simulation.environment.live_document.binding.get',
                 'simulation.environment.live_document.rebind','simulation.environment.live_document.inventory.apply'):
        d = registry.items[name][2]
        assert d.lifecycle_status.value == 'experimental'
        assert {key for key,value in d.exposure.model_dump().items() if value} == {'web'}
    connectors.bound_runtime_for_user = lambda *_: None
    with pytest.raises(CapabilityBusinessError): handler({},ctx)
    assert len(queued) == 1


def test_teamcenter_requests_are_web_only_with_action_specific_effects():
    registry = Registry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(Connectors(), clock=lambda: NOW))
    expectations = {
        'simulation.teamcenter.product.search.request': 'exact, prefix, and contains search',
        'simulation.teamcenter.revision_rule.search.request': 'revision rules',
        'simulation.teamcenter.product_structure.observe.request': 'product structure',
        'simulation.teamcenter.product_structure.page.read.request': 'occurrence rows',
        'simulation.teamcenter.visualization.launch.request': 'new VisMockup document',
        'simulation.teamcenter.visualization.insert.request': 'active VisMockup document',
    }
    for capability_id, phrase in expectations.items():
        descriptor = registry.items[capability_id][2]
        assert {key for key, value in descriptor.exposure.model_dump().items() if value} == {'web'}
        assert descriptor.resource_selectors
        assert phrase in descriptor.business_effect


def test_hierarchy_inventory_request_has_bounded_input_and_operation_receipt():
    connectors = Connectors(); control = ConnectorControlPlane(connectors, clock=lambda: NOW)
    registry = Registry(); register_connector_runtime_capabilities(registry, control)
    spec, _handler, _descriptor = registry.items['simulation.vismockup.document.hierarchy_inventory.read.request']
    assert spec.input_schema['properties']['page_size']['maximum'] == 16
    assert spec.input_schema['properties']['max_nodes']['maximum'] == 100000
    assert spec.output_schema['required'] == ['operation_id', 'status', 'version']
