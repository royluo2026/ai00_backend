from copy import deepcopy
from datetime import UTC,datetime,timedelta
import hashlib
import json
import sqlite3
from types import SimpleNamespace
import pytest
from backend.capability_v2.provider_contracts import CapabilityContext,CapabilityBusinessError
from plugins.simulation.tests.test_live_document_binding_repository import database,seed_teamcenter_online_workspace
from plugins.simulation.simulation_backend.data import workspace_repository
from plugins.simulation.simulation_backend.capabilities.cache_source_open import CacheSourceOpenProvider,specs
from plugins.simulation.simulation_backend.application.cache_open_evidence import CACHE_OPEN_CONTRACT_HASH,cache_package_hash

IDENTITY=dict(batch_id='a'*32,generation=None,snapshot_hash=None,schema_version=1)
MATRIX=[1,0,0,0,0,1,0,0,0,0,1,0,2,3,4,1]
REF=dict(dataset_uid='dataset',file_uid='file',file_name='part.jt',relation_type='IMAN_Rendering')
ARTIFACT=dict(artifact_id='jt-immutable',media_type='model/jt',sha256='d'*64,byte_size=80,version=1)
NOW=datetime(2026,9,28,tzinfo=UTC)

@pytest.fixture
def case(database):
    seed_teamcenter_online_workspace(database)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE workmanship_sim_vm_documents SET source_kind='teamcenter_cache_snapshot',artifact_ref_json=?",(json.dumps({'cache_binding':IDENTITY}),))
        db.execute('CREATE TABLE workmanship_sim_connector_runtime_plans (plan_id TEXT,actor_gid TEXT,tenant_gid TEXT,plan_json TEXT)')
    state=SimpleNamespace(reads=0,receipts=0,creates=0,queue=[],available=True,candidate=True,authorizations=0)
    node=dict(node_key='root',parent_node_key=None,name='Root',item_revision_uid='revision',root_transform=MATRIX,
        relative_transform=None,absolute_transform=MATRIX,absolute_read_state='value',transform_state='root_absolute',geometry_refs=[REF],error_code=None)
    state.projection=dict(identity=IDENTITY,nodes=[node],spatial_authority={'unit':'m','evidence':'documented'})
    def read(*args):state.reads+=1;return deepcopy(state.projection)
    def receipt(binding,members,*args,**kwargs):
        state.receipts+=len(members)
        results=[{'operation_id':'file-operation','status':'completed','file':{'artifact_ref':ARTIFACT}} if state.available else None for member in members]
        return dict(identity=binding,results=results,missing_count=sum(value is None for value in results))
    def candidates(*args,**kwargs):
        return dict(identity=IDENTITY,next_cursor=None,receipts=[dict(node_key='root',item_revision_uid='revision',dataset_uid='dataset',file_uid='file')] if state.candidate else [])
    def create(content,media_type,context,**kwargs):
        state.creates+=1
        return dict(artifact_id='package',media_type=media_type,sha256=hashlib.sha256(content).hexdigest(),byte_size=len(content),version=1)
    def authorize(*args,**kwargs):state.authorizations+=1;return ARTIFACT
    state.runtime=dict(device_id='device',owner_user_gid='30',tenant_gid='20',status='active',runtime_type='electron',
        protocol='ai00.connector.execution-plan.v2',session_token_hash='token',runtime_generation=1,current_runtime_instance_id='instance',
        heartbeat_at=NOW,session_expires_at=NOW+timedelta(minutes=10),adapter_health_json=dict(runtime_generation=1,runtime_instance_id='instance',
            adapter=dict(adapter_id='ai00.vismockup',operations=[dict(operation_id='vismockup.model.open@2',contract_hash=CACHE_OPEN_CONTRACT_HASH)])))
    connector=SimpleNamespace(clock=lambda:NOW,repository=SimpleNamespace(bound_runtime_for_user=lambda *args:state.runtime),
        queue_v2=lambda plan,*args,**kwargs:state.queue.append(plan))
    cache=SimpleNamespace(_read=lambda *args:None,repo=SimpleNamespace(query_pinned=lambda *args,**kwargs:dict(identity=IDENTITY)))
    state.provider=CacheSourceOpenProvider(SimpleNamespace(cache=cache,connector=connector),connect=workspace_repository.get_simulation_conn,
        reader=read,find_bulk=receipt,create=create,authorize=authorize,list_receipts=candidates)
    state.context=CapabilityContext(source='web',user_gid='30',team_gid='20',request_id='request',idempotency_key='request',
        normalized_input_hash='sha256:'+'e'*64,capability_version_gid='cv2_'+'a'*24,business_definition_hash='sha256:'+'a'*64,catalog_release='rel_example')
    state.payload=dict(workspace_gid='10',document_gid='11')
    return state

def admit(case,payload=None):
    inspection=case.provider.inspect(case.payload,case.context).data
    request={**case.payload,'expected_workspace_row_version':1,'materialization_hash':inspection['materialization_hash'],**(payload or {})}
    prepared=case.provider.prepare(request,case.context)
    with workspace_repository.get_simulation_conn() as conn,conn.cursor() as cur:
        return case.provider.admit(request,case.context,cur,prepared=prepared).data


def test_environment_context_is_owned_and_names_one_environment_document(case,database):
    from xml.etree import ElementTree as ET
    with sqlite3.connect(database) as db:
        db.execute("UPDATE workmanship_sim_workspaces SET name='W10 test2'")
    page=case.provider.inspect(case.payload,case.context).data
    prepared=case.provider.prepare({**case.payload,'expected_workspace_row_version':1,
                                   'materialization_hash':page['materialization_hash']},case.context)
    xml=ET.fromstring(prepared['package'].plmxml)
    ns={'p':'http://www.plmxml.org/Schemas/PLMXMLSchema'}
    values={p.get('title'):p.get('value') for p in xml.findall('p:UserData/p:UserValue',ns)}
    assert xml.get('name')=='W10 test2'
    assert values['ai00_environment_gid']=='10'
    assert values['ai00_source_document_gid']=='11'
    assert values['ai00_cache_layout']=='frozen_absolute_geometry.v1'


def test_inspect_fixed_nodes_and_verified_receipt_then_single_exact_open_and_replay(case):
    page=case.provider.inspect(case.payload,case.context).data
    assert page['identity']==IDENTITY and page['file_count']==1
    assert page['files'][0]['operation_id']=='file-operation'
    result=admit(case)
    assert result==admit(case)
    assert case.creates==1 and len(case.queue)==1 and case.authorizations==1
    plan=case.queue[0];step=plan['steps'][0]
    assert plan['capability_id']=='simulation.environment.cache_source.open.request'
    assert len(plan['steps'])==1 and step['operation_id']=='vismockup.model.open@2'
    assert step['post_condition_probe_id']=='vismockup.application.probe@1' and step['timeout_seconds']==600
    assert step['side_effect_classification']=='write' and step['contract_hash']==CACHE_OPEN_CONTRACT_HASH
    packet=step['payload']
    assert packet['package_hash']==cache_package_hash({key:value for key,value in packet.items() if key!='package_hash'})
    assert list(result['node_map'])==['root']
    assert set(result['node_map']['root'])=={'instance_id','parent_node_key'}
    assert result['node_map']['root']['parent_node_key'] is None
    assert result['node_map']['root']['instance_id'] and packet['package_dependencies'][0]['artifact_ref']==ARTIFACT

def test_missing_index_candidates_never_read_full_member_properties(case):
    case.candidate=False
    page=case.provider.inspect(case.payload,case.context).data
    assert page['files'][0]['operation_id'] is None and case.receipts==0
    case.available=False
    with pytest.raises(CapabilityBusinessError,match='cache_package_file_missing'):admit(case)
    assert case.creates==0 and not case.queue


def test_scope_survives_inspection_admission_and_hash_prevents_scope_swap(case):
    root=case.projection['nodes'][0]
    case.projection['nodes'] += [{**deepcopy(root),'node_key':key,'parent_node_key':'root',
        'transform_state':'source_validated','geometry_refs':[{**REF,'file_uid':key}]} for key in ('a','b')]
    whole=case.provider.inspect(case.payload,case.context).data
    case.payload['root_node_key']='a'
    scoped=case.provider.inspect(case.payload,case.context).data
    assert scoped['file_count']==1 and scoped['files'][0]['file_uid']=='a'
    assert scoped['materialization_hash']!=whole['materialization_hash']
    with pytest.raises(CapabilityBusinessError,match='cache_materialization_changed'):
        admit(case,{'materialization_hash':whole['materialization_hash']})
    result=admit(case)
    assert list(result['node_map'])==['a']
    assert result['node_map']['a']['parent_node_key'] is None

@pytest.mark.parametrize('change',['version','hash','owner','runtime','contract','receipt','rawnodes'])
def test_no_artifact_or_native_effect_for_invalid_request(case,database,change):
    payload={}
    if change=='version':payload['expected_workspace_row_version']=2
    elif change=='hash':payload['materialization_hash']='sha256:'+'0'*64
    elif change=='owner':
        with sqlite3.connect(database) as db:db.execute("UPDATE workmanship_sim_workspaces SET owner_gid='99'")
    elif change=='runtime':case.runtime['status']='revoked'
    elif change=='contract':case.runtime['adapter_health_json']['adapter']['operations']=[]
    elif change=='receipt':case.available=False
    elif change=='rawnodes':payload['nodes']=[]
    with pytest.raises(CapabilityBusinessError):admit(case,payload)
    assert case.creates==0 and not case.queue

def test_inspection_reuses_bounded_projection_but_rechecks_source_owner(case,database):
    first=case.provider.inspect(case.payload,case.context).data
    assert case.provider.inspect(case.payload,case.context).data==first and case.reads==1
    with sqlite3.connect(database) as db:db.execute("UPDATE workmanship_sim_vm_documents SET owner_gid='99'")
    with pytest.raises(CapabilityBusinessError):case.provider.inspect(case.payload,case.context)

def test_specs_closed_inputs_large_bounded_output_and_owned_version_policy():
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
    for spec,_ in specs():
        descriptor=descriptor_for(spec)
        assert descriptor.exposure.web and not descriptor.exposure.agent
        assert spec.input_schema['additionalProperties'] is False
        assert descriptor.execution_budget.max_output_bytes>=8*1024*1024
        if spec.id.endswith('open.request'):
            assert descriptor.expected_version_payload_path=='expected_workspace_row_version'
            assert descriptor.confirmation_policy=='none'


def test_durable_plan_survives_missing_gateway_response_without_second_open(case,database):
    first=admit(case)
    with sqlite3.connect(database) as db:
        db.execute('DELETE FROM workmanship_sim_workspace_idempotency')
        plan=case.queue[0]
        db.execute('INSERT INTO workmanship_sim_connector_runtime_plans VALUES (?,?,?,?)',
            (plan['plan_id'],'30','20',json.dumps(plan)))
    recovered=admit(case)
    assert recovered==first and len(case.queue)==1 and case.creates==1


def test_public_mapping_preserves_parent_keys_without_repeated_instance_paths(case):
    child={**deepcopy(case.projection['nodes'][0]),'node_key':'child','parent_node_key':'root',
        'transform_state':'source_validated','relative_transform':MATRIX,'geometry_refs':[]}
    case.projection['nodes'].append(child)
    result=admit(case)
    assert set(result['node_map'])=={'root','child'}
    assert result['node_map']['child']['parent_node_key']=='root'
    assert all(set(value)=={'instance_id','parent_node_key'} for value in result['node_map'].values())


def test_complete_simulation_registration_builds_governed_cache_descriptors():
    from plugins.simulation.simulation_backend.capabilities import register_capabilities
    registered={}
    class Registry:
        def register(self,spec,handler,*,descriptor):
            key=(spec.id,spec.version)
            assert key not in registered
            registered[key]=(handler,descriptor)
    register_capabilities(Registry())
    for name in ('materialization.inspect','open.request','live_document.bind'):
        handler,descriptor=registered[('simulation.environment.cache_source.'+name,1)]
        assert descriptor.capability_version_gid
        if name=='open.request':assert handler.__capability_transactional__


def test_final_admission_rechecks_version_after_preparation(case,database):
    inspection=case.provider.inspect(case.payload,case.context).data
    payload={**case.payload,'expected_workspace_row_version':1,'materialization_hash':inspection['materialization_hash']}
    prepared=case.provider.prepare(payload,case.context)
    with sqlite3.connect(database) as db:db.execute('UPDATE workmanship_sim_workspaces SET row_version=2')
    with workspace_repository.get_simulation_conn() as conn,conn.cursor() as cursor:
        with pytest.raises(CapabilityBusinessError,match='version_conflict'):case.provider.admit(payload,case.context,cursor,prepared=prepared)
    assert case.creates==0 and not case.queue


def test_runtime_is_rechecked_after_preparation_and_before_queue(case):
    inspection=case.provider.inspect(case.payload,case.context).data
    payload={**case.payload,'expected_workspace_row_version':1,'materialization_hash':inspection['materialization_hash']}
    prepared=case.provider.prepare(payload,case.context)
    case.runtime['status']='revoked'
    with workspace_repository.get_simulation_conn() as conn,conn.cursor() as cursor:
        with pytest.raises(CapabilityBusinessError,match='connector_offline'):case.provider.admit(payload,case.context,cursor,prepared=prepared)
    assert case.creates==0 and not case.queue


@pytest.mark.parametrize('fail',[False,True])
def test_artifact_authorization_four_workers_settle_and_deny_before_effect(case,fail):
    from threading import Barrier,Lock
    from contextvars import ContextVar
    scope=ContextVar('test_cache_authorization_scope');scope.set('caller')
    case.projection['nodes'][0]['geometry_refs']=[{**REF,'file_uid':str(index)} for index in range(8)]
    barrier=Barrier(4);lock=Lock();state=dict(active=0,peak=0,called=0)
    def authorize(ref,context,*,resource_refs):
        assert scope.get()=='caller'
        assert context is case.context and ref==ARTIFACT
        assert resource_refs==('simulation://model-cache/'+IDENTITY['batch_id'],)
        with lock:
            state['active']+=1;state['called']+=1
            call=state['called'];state['peak']=max(state['peak'],state['active'])
        try:
            if not fail or call<=4:barrier.wait(timeout=10)
            if fail and call==1:raise ValueError('authorization denied')
            return ref
        finally:
            with lock:state['active']-=1
    case.provider.authorize=authorize
    if fail:
        with pytest.raises(CapabilityBusinessError):admit(case)
        assert case.creates==0 and not case.queue
    else:
        admit(case)
        assert state['called']==8 and case.creates==1 and len(case.queue)==1
    assert state['peak']==4 and state['active']==0
