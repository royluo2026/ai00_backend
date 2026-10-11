"""Exercise the actual registered cache handlers through the strong-write Gateway."""
import asyncio
from contextlib import contextmanager
from datetime import datetime,UTC
import json
import sqlite3
from types import SimpleNamespace

import pytest

from plugins.simulation.tests.test_cloud_model_cache import store,Cursor
from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CloudModelCacheRepository
from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import CloudModelCacheProvider,specs,WORKER_ID
from plugins.simulation.simulation_backend.capabilities.provider import register
from plugins.simulation.simulation_backend.data import connection as domain_connection
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationGrants
from backend.capability_v2.catalog import CatalogResolver,build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import ActorIdentity,ConsumerDescriptor,ConsumerIdentity,ConsumerType,InvocationEnvelope,TenantIdentity
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
from backend.capability_v2.outcomes import SqlOutcomeStore
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.reliability import ApprovalService,InMemoryApprovalStore,InMemoryRateLimiter,ReliabilityCoordinator
from plugins.project_management.project_management_backend.capabilities.reviewed import register_reviewed_capabilities
from plugins.project_management.project_management_backend.application.outcomes import project_outcome_port
from plugins.project_management.project_management_backend.application.service import ProjectManagementApplication


class OutcomeCursor(Cursor):
    def fetchone(self):
        row=super().fetchone()
        if row:
            for key in ('started_at','completed_at'):
                if isinstance(row.get(key),str):row[key]=datetime.fromisoformat(row[key])
        return row
    @property
    def rowcount(self):return self.raw.rowcount


class Transaction:
    def __init__(self,path):
        self.raw=sqlite3.connect(path,check_same_thread=False)
        self.raw.row_factory=sqlite3.Row
        self.raw.execute('BEGIN')
    def cursor(self,*args):return OutcomeCursor(self.raw)
    def commit(self):self.raw.commit()
    def rollback(self):self.raw.rollback()
    def close(self):self.raw.close()


@pytest.fixture
def cache_gateway(store,monkeypatch):
    monkeypatch.setattr('backend.platform_sdk.access.build_access_scope',lambda user:{'team_gids':[user['team_id'],'10']})
    with store() as conn,conn.cursor() as cur:
        cur.execute('PRAGMA database_list');path=cur.fetchone()['file']
        cur.execute('CREATE TABLE workmanship_base_capability_outcomes ('
            'operation_id TEXT PRIMARY KEY,request_id TEXT,idempotency_scope TEXT UNIQUE,payload_hash TEXT,'
            'capability_id TEXT,major_version INTEGER,tenant_id TEXT,consumer_scope TEXT,actor_id TEXT,'
            'consumer_type TEXT,consumer_id TEXT,consumer_instance_id TEXT,policy_version TEXT,status TEXT,'
            'result_json TEXT,started_at TEXT,completed_at TEXT)')
        cur.execute('CREATE TABLE workmanship_base_capability_audit_outbox ('
            'event_id TEXT PRIMARY KEY,operation_id TEXT UNIQUE,event_type TEXT,payload_json TEXT,'
            'created_at TEXT,delivered_at TEXT,attempt_count INTEGER DEFAULT 0,last_error_code TEXT)')
    @contextmanager
    def connections():
        tx=Transaction(path)
        try:yield tx;tx.commit()
        except BaseException:tx.rollback();raise
        finally:tx.close()
    monkeypatch.setattr(domain_connection,'open_simulation_transaction',lambda:Transaction(path))
    project_row=dict(gid='3',team_id='2',owner_gid='1',name='Project',status='active',share_scope='team',
        created_at='2026-09-28T00:00:00Z',updated_at='2026-09-28T00:00:00Z',meta={'empty':'','nested':{'zero':0}})
    monkeypatch.setattr(project_outcome_port,'provider',ProjectManagementApplication(SimpleNamespace(get_project=lambda gid:project_row if gid=='3' else None)))
    connector=SimpleNamespace(repository=SimpleNamespace(bound_runtime_for_user=lambda *_:None))
    provider=CloudModelCacheProvider(CloudModelCacheRepository(store),connector)
    registry=CapabilityRegistry()
    register_reviewed_capabilities(registry)
    for spec,handler in specs(provider):register(registry,spec,handler)
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_files import CacheFileProvider,specs as file_specs
    for spec,handler in file_specs(CacheFileProvider(provider,connector)):register(registry,spec,handler)
    release=build_release([item.descriptor for item in registry.snapshot()])
    catalogs=InMemoryCatalogStore();catalogs.publish(release)
    approvals=ApprovalService(InMemoryApprovalStore())
    grants=AuthorizationGrants(permissions=('simulation.use','project.view'),resource_scopes=('*',),data_scopes=('confidential',),policy_version='cache-test-1',tenant_id='2')
    policy=LegacyServerGatewayPolicy(lambda user:{'gid':user,'is_active':True},lambda *_:grants,approvals)
    gateway=CapabilityGatewayService(CatalogResolver(catalogs,registry),policy,reliability=ReliabilityCoordinator(SqlOutcomeStore(connections),InMemoryRateLimiter(limit=100))).bind_release(release.release_id)
    monkeypatch.setattr('backend.capability_v2.gateway.get_default_gateway',lambda:gateway)
    def envelope(name,payload,key,expected=None):
        worker=name=='advance'
        identity=ConsumerIdentity(actor=ActorIdentity(user_id='1',authentication_method='jwt',authenticated_at=datetime.now(UTC)),tenant=TenantIdentity(tenant_id='2',membership='member',active_roles=('super_admin',)),consumer=ConsumerDescriptor(type=ConsumerType.WORKER if worker else ConsumerType.WEB,consumer_id=WORKER_ID if worker else DESKTOP_CONSUMER_ID))
        return InvocationEnvelope(capability_id='simulation.model_cache.'+name,major_version=1,catalog_release=release.release_id,payload=payload,identity=identity,request_id=key,trace_id=key,idempotency_key=key,expected_resource_version=str(expected) if expected else None)
    def invoke(name,payload,key,expected=None):return asyncio.run(gateway.invoke(envelope(name,payload,key,expected)))
    return SimpleNamespace(invoke=invoke,envelope=envelope,gateway=gateway,connections=connections,provider=provider,registry=registry,policy=policy,project_row=project_row)


def create_payload():
    return dict(project_gid='3',project_name='Project',phase='TG0',source_selector=dict(endpoint_id='tc-production',object_uid='root',item_revision_uid='',bom_view_uid='',revision_rule='Latest Working',configuration_date='2026-09-28T00:00:00Z'),trigger_kind='manual')


def test_file_admission_uses_gateway_provenance_and_transactional_replay(cache_gateway,store):
    from plugins.simulation.tests.test_cache_file_materialization import file_snapshot
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
    from backend.capability_v2.contracts import OperationRef,OperationStatus
    g=cache_gateway;repo,batch,ref=file_snapshot(store);plans=[];now=datetime.now(UTC)
    operation,contract=DIRECT_VISMOCKUP_OPERATIONS['tc_file']
    connector=g.provider.connector
    connector.clock=lambda:now
    connector.repository.bound_runtime_for_user=lambda *_:{'device_id':'device','heartbeat_at':now,'session_expires_at':now+__import__('datetime').timedelta(minutes=5),'runtime_generation':1,'current_runtime_instance_id':'instance','adapter_health_json':{'runtime_generation':1,'runtime_instance_id':'instance','adapter':{'adapter_id':'ai00.vismockup','operations':[{'operation_id':operation,'contract_hash':contract}]}}}
    connector.repository.get_plan_result=lambda *_:None
    def admit(plan,*_,**kw):plans.append(plan);return OperationRef(operation_id=plan['plan_id'],status=OperationStatus.ACCEPTED)
    connector.queue_v2=admit
    payload={'batch_id':batch['batch_id'],'node_key':'root','dataset_uid':'dataset','file_uid':'file','expected_generation':'a'*32}
    first=g.invoke('file.fetch.request',payload,'file-gateway-key')
    assert first.ok,first.error
    second=g.invoke('file.fetch.request',payload,'file-gateway-key')
    assert second.ok and second.data==first.data
    assert len(plans)==1
    plan=plans[0]
    assert plan['capability_version_gid'].startswith('cv2_') and plan['business_definition_hash'].startswith('sha256:')
    assert plan['steps'][0]['operation_id']==operation and plan['steps'][0]['payload']['file_ref']==ref
    with g.connections() as conn,conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_base_capability_outcomes WHERE status=%s',('completed',))
        assert cur.fetchone()['count']==1


def test_batch_file_capabilities_are_registered_in_gateway(cache_gateway):
    registered={capability_id for capability_id,_ in cache_gateway.registry.keys()}
    assert {
        'simulation.model_cache.file.fetch.batch.request',
        'simulation.model_cache.file.fetch.batch.result',
    } <= registered


def test_batch_file_admission_uses_one_fixed_plan_with_preflight_and_member_steps(cache_gateway,store):
    from plugins.simulation.tests.test_cache_file_materialization import file_snapshot
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
    from backend.capability_v2.contracts import OperationRef,OperationStatus
    g=cache_gateway;repo,batch,ref=file_snapshot(store);plans=[];now=datetime.now(UTC)
    fetch,fetch_hash=DIRECT_VISMOCKUP_OPERATIONS['tc_file'];preflight,preflight_hash=DIRECT_VISMOCKUP_OPERATIONS['tc_file_preflight']
    connector=g.provider.connector;connector.clock=lambda:now
    connector.repository.bound_runtime_for_user=lambda *_:{'device_id':'device','heartbeat_at':now,'session_expires_at':now+__import__('datetime').timedelta(minutes=5),'runtime_generation':1,'current_runtime_instance_id':'instance','adapter_health_json':{'runtime_generation':1,'runtime_instance_id':'instance','adapter':{'adapter_id':'ai00.vismockup','operations':[{'operation_id':fetch,'contract_hash':fetch_hash},{'operation_id':preflight,'contract_hash':preflight_hash}]}}}
    connector.repository.get_plan_result=lambda *_:None
    connector.queue_v2=lambda plan,*_,**kw:(plans.append(plan) or OperationRef(operation_id=plan['plan_id'],status=OperationStatus.ACCEPTED))
    payload={'batch_id':batch['batch_id'],'expected_generation':'a'*32,'files':[{'node_key':'root','dataset_uid':'dataset','file_uid':'file'}]}
    first=g.invoke('file.fetch.batch.request',payload,'batch-file-gateway-key')
    second=g.invoke('file.fetch.batch.request',payload,'batch-file-gateway-key')
    assert first.ok,first.error
    assert second.ok and second.data==first.data
    assert len(plans)==1
    plan=plans[0]
    assert plan['capability_id']=='simulation.model_cache.file.fetch.batch.request'
    assert [step['operation_id'] for step in plan['steps']]==[preflight,fetch]
    assert plan['steps'][0]['contract_hash']==preflight_hash
    assert plan['steps'][0]['payload']['files'][0]['file_ref']==ref
    assert plan['steps'][1]['payload']['file_ref']==ref


def test_gateway_cache_create_control_and_worker_writes_commit_and_replay(cache_gateway):
    g=cache_gateway
    for name in ('create','control','advance'):
        assert getattr(g.registry.get('simulation.model_cache.'+name,1).handler,'__capability_transactional__',False)
    created=g.invoke('create',create_payload(),'create-gateway')
    assert created.ok,created.error
    assert created.data['display_name']=='v1'
    replay=g.invoke('create',create_payload(),'create-gateway')
    assert replay.ok and replay.data==created.data and replay.operation_ref==created.operation_ref
    bid=created.data['batch_id']
    paused=g.invoke('control',dict(batch_id=bid,action='pause',expected_version=1),'pause-gateway',1)
    assert paused.ok and paused.data['status']=='paused',paused.error
    resumed=g.invoke('control',dict(batch_id=bid,action='resume',expected_version=2),'resume-gateway',2)
    assert resumed.ok and resumed.data['status']=='queued',resumed.error
    advanced=g.invoke('advance',dict(batch_id=bid),'advance-gateway')
    assert advanced.ok and advanced.data['status']=='waiting_connector',advanced.error
    with g.connections() as tx,tx.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_base_capability_outcomes WHERE status=%s',('completed',));assert cur.fetchone()['count']==4
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_base_capability_audit_outbox');assert cur.fetchone()['count']==4
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_batches');assert cur.fetchone()['count']==1
        cur.execute('SELECT next_version FROM workmanship_sim_cloud_cache_versions');assert cur.fetchone()['next_version']==2


def test_cache_creation_uses_the_real_registered_project_reader(cache_gateway):
    g=cache_gateway
    result=g.invoke('create',create_payload(),'real-project-gateway')
    assert result.ok,result.error
    assert result.data['project_name']=='Project'
    assert g.provider.project_reader is None
    spec=g.registry.get('project.project.read.atomic.projects_get',2).spec
    assert spec.output_schema['additionalProperties'] is False


def test_registered_project_read_rejects_foreign_tenant_before_cache_creation(cache_gateway):
    g=cache_gateway;g.project_row['team_id']='99'
    result=g.invoke('create',create_payload(),'foreign-project-gateway')
    assert not result.ok and result.error.code=='forbidden'
    with g.connections() as tx,tx.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_batches');assert cur.fetchone()['count']==0


def test_cache_creation_handles_legacy_unowned_project_through_owner_policy(cache_gateway):
    g=cache_gateway;g.project_row['team_id']=None
    result=g.invoke('create',create_payload(),'legacy-project-gateway')
    assert result.ok,result.error
    assert result.data['project_gid']=='3' and g.project_row['team_id'] is None


def test_cache_creation_accepts_parent_team_project_without_rewriting_ownership(cache_gateway):
    g=cache_gateway;g.project_row['team_id']='10'
    result=g.invoke('create',create_payload(),'parent-project-gateway')
    assert result.ok,result.error
    assert g.project_row['team_id']=='10'
    with g.connections() as tx,tx.cursor() as cur:
        cur.execute('SELECT tenant_gid FROM workmanship_sim_cloud_cache_batches WHERE batch_id=%s',(result.data['batch_id'],))
        assert cur.fetchone()['tenant_gid']=='2'


@pytest.mark.parametrize('failure',['projection','outbox'])
def test_gateway_failure_rolls_back_batch_root_task_and_version(cache_gateway,failure):
    g=cache_gateway
    if failure=='projection':
        def reject(*args):raise ValueError('injected projection failure')
        g.policy.project=reject
    else:
        with g.connections() as tx,tx.cursor() as cur:
            cur.execute("CREATE TRIGGER fail_cache_outbox BEFORE INSERT ON workmanship_base_capability_audit_outbox BEGIN SELECT RAISE(ABORT,'injected outbox failure'); END")
    result=g.invoke('create',create_payload(),'failure-gateway')
    assert not result.ok
    assert result.error.code==('provider_failed' if failure=='projection' else 'outcome_persistence_failed')
    with g.connections() as tx,tx.cursor() as cur:
        for name in ('batches','tasks','versions'):
            cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_'+name);assert cur.fetchone()['count']==0


def test_repository_borrowed_transaction_rolls_back_only_the_rejected_page(cache_gateway):
    g=cache_gateway
    created=g.invoke('create',create_payload(),'page-gateway');assert created.ok,created.error
    bid=created.data['batch_id']
    with g.connections() as tx:
        bound=g.provider.repo.in_transaction(tx)
        task=bound.dispatch(bid,'2',lambda *_:'operation-page')
        from plugins.simulation.tests.test_cloud_model_cache import page
        with pytest.raises(ValueError,match='cache_generation_stale'):
            bound.apply_result(bid,'2',task,page(created.data,generation='bad'),'sha256:'+'c'*64)
        bound.failure(bid,'2','cache_generation_stale',task)
    with g.connections() as tx,tx.cursor() as cur:
        cur.execute('SELECT principal_hash,status FROM workmanship_sim_cloud_cache_batches WHERE batch_id=%s',(bid,))
        assert cur.fetchone()=={'principal_hash':None,'status':'needs_refresh'}


def test_worker_handler_locks_batch_before_ordinary_snapshot_reads(cache_gateway,monkeypatch):
    g=cache_gateway
    created=g.invoke('create',create_payload(),'lock-gateway');assert created.ok,created.error
    calls=[]
    original=CloudModelCacheRepository._batch
    def tracked(cur,batch_id,tenant_gid,lock=False):
        calls.append(lock)
        return original(cur,batch_id,tenant_gid,lock)
    monkeypatch.setattr(CloudModelCacheRepository,'_batch',staticmethod(tracked))
    result=g.invoke('advance',dict(batch_id=created.data['batch_id']),'lock-worker-gateway')
    assert result.ok,result.error
    assert calls and calls[0] is True


@pytest.mark.parametrize('rollback',[False,True])
def test_gateway_bulk_receipt_rows_continuation_and_outcome_share_one_commit(cache_gateway,rollback):
    from plugins.simulation.tests.test_cloud_model_cache_bulk import snapshot_page,PRINCIPAL
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
    g=cache_gateway;created=g.invoke('create',create_payload(),'bulk-gateway-create');assert created.ok,created.error
    batch=created.data;operation,contract=DIRECT_VISMOCKUP_OPERATIONS['tc_cache_v2'];plans={}
    health=dict(runtime_generation=1,runtime_instance_id='instance',adapter={'operations':[dict(operation_id=operation,contract_hash=contract)]})
    runtime=dict(runtime_type='electron',device_id='device',runtime_generation=1,current_runtime_instance_id='instance',adapter_health_json=json.dumps(health))
    repository=g.provider.connector.repository
    repository.bound_runtime_for_user=lambda *_:runtime
    repository.get_plan_result=lambda plan,*_:plans.get(plan)
    def queue(plan,context,**kwargs):
        assert plan['steps'][0]['operation_id']==operation
        plans[plan['plan_id']]=dict(status='completed',outcome={'steps':[{'result':dict(principal_hash=PRINCIPAL,result_json=json.dumps(snapshot_page(batch,0,count=3,size=2)))}]})
        return SimpleNamespace(operation_id=plan['plan_id'])
    g.provider.connector.queue_v2=queue;g.provider.connector.clock=lambda:datetime.now(UTC)
    if rollback:
        with g.connections() as tx,tx.cursor() as cur:cur.execute("CREATE TRIGGER fail_bulk_outbox BEFORE INSERT ON workmanship_base_capability_audit_outbox BEGIN SELECT RAISE(ABORT,'injected outbox failure'); END")
    result=g.invoke('advance',dict(batch_id=batch['batch_id']),'bulk-gateway-advance')
    assert result.ok is (not rollback),result.error
    with g.connections() as tx,tx.cursor() as cur:
        cur.execute('SELECT node_count FROM workmanship_sim_cloud_cache_batches WHERE batch_id=%s',(batch['batch_id'],));assert cur.fetchone()['node_count']==(0 if rollback else 2)
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_receipts');assert cur.fetchone()['count']==(0 if rollback else 1)
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_tasks WHERE kind='snapshot'");assert cur.fetchone()['count']==(0 if rollback else 2)
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_base_capability_outcomes WHERE status='completed'");assert cur.fetchone()['count']==(1 if rollback else 2)


@pytest.mark.parametrize('abandonment',['cancel','timeout'])
def test_gateway_abandonment_rolls_back_and_closes_open_participant(cache_gateway,monkeypatch,abandonment):
    g=cache_gateway;events=[]
    original=domain_connection.open_simulation_transaction
    def tracked():
        tx=original()
        rollback,close,commit=tx.rollback,tx.close,tx.commit
        def wrap(name,call):
            def run():events.append(name);return call()
            return run
        tx.rollback=wrap('rollback',rollback);tx.close=wrap('close',close);tx.commit=wrap('commit',commit)
        return tx
    monkeypatch.setattr(domain_connection,'open_simulation_transaction',tracked)
    async def scenario():
        entered=asyncio.Event()
        async def delayed(*args):
            entered.set()
            await asyncio.Event().wait()
        g.provider.project_reader=delayed
        if abandonment=='timeout':g.gateway._provider_timeout_seconds=lambda *_:0.05
        task=asyncio.create_task(g.gateway.invoke(g.envelope('create',create_payload(),'abandon-'+abandonment)))
        await asyncio.wait_for(entered.wait(),1)
        if abandonment=='cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        else:
            result=await task
            assert not result.ok and result.error.code=='runtime_timeout'
    asyncio.run(scenario())
    assert events==['rollback','close']
    with g.connections() as tx,tx.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_batches');assert cur.fetchone()['count']==0
