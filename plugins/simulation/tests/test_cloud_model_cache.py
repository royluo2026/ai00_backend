import json
import sqlite3
import uuid
import asyncio
from pathlib import Path
from contextlib import contextmanager

import pytest

from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CloudModelCacheRepository, CacheError


class Cursor:
    def __init__(self, conn): self.raw = conn.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.raw.close()
    def execute(self, sql, params=()):
        self.raw.execute(sql.replace('%s', '?').replace(' FOR UPDATE', '').replace('INSERT IGNORE INTO','INSERT OR IGNORE INTO'), params)
    def executemany(self, sql, params):
        self.raw.executemany(sql.replace('%s', '?'),params)
    def fetchone(self):
        row = self.raw.fetchone()
        return dict(row) if row else None
    def fetchall(self): return [dict(row) for row in self.raw.fetchall()]
    def fetchmany(self, size): return [dict(row) for row in self.raw.fetchmany(size)]


@pytest.fixture
def store():
    path = Path('.cache-test-' + uuid.uuid4().hex + '.sqlite')
    conn = sqlite3.connect(path)
    conn.executescript('''
      CREATE TABLE workmanship_sim_cloud_cache_batches(batch_id TEXT PRIMARY KEY,tenant_gid TEXT,actor_gid TEXT,project_gid TEXT,project_name TEXT,phase TEXT,display_name TEXT,selector_json TEXT,source_hash TEXT,status TEXT,created_at TEXT,updated_at TEXT,completed_at TEXT,row_version INTEGER,node_count INTEGER,fields_json TEXT,error_code TEXT,trigger_kind TEXT,request_key TEXT,request_hash TEXT,connector_device_id TEXT,principal_hash TEXT,preparation_status TEXT DEFAULT 'not_prepared',preparation_error TEXT, UNIQUE(tenant_gid,actor_gid,request_key));
      CREATE TABLE workmanship_sim_cloud_cache_tasks(batch_id TEXT,task_key TEXT,kind TEXT,payload_json TEXT,status TEXT,operation_id TEXT,attempt INTEGER, PRIMARY KEY(batch_id,task_key));
      CREATE TABLE workmanship_sim_cloud_cache_nodes(batch_id TEXT,node_key TEXT,data_json TEXT,snapshot_generation TEXT,snapshot_position INTEGER, PRIMARY KEY(batch_id,node_key),UNIQUE(batch_id,snapshot_generation,snapshot_position));
      ALTER TABLE workmanship_sim_cloud_cache_nodes ADD COLUMN parent_node_key TEXT GENERATED ALWAYS AS (json_extract(data_json,'$.structure.parent_occurrence_id')) VIRTUAL;
      ALTER TABLE workmanship_sim_cloud_cache_nodes ADD COLUMN sibling_order INTEGER GENERATED ALWAYS AS (json_extract(data_json,'$.structure.child_order')) VIRTUAL;
      CREATE INDEX ix_cloud_cache_parent_order ON workmanship_sim_cloud_cache_nodes(batch_id,parent_node_key,sibling_order,node_key);
      CREATE TABLE workmanship_sim_cloud_cache_manifests(batch_id TEXT PRIMARY KEY,manifest_json TEXT);
      CREATE TABLE workmanship_sim_cloud_cache_receipts(batch_id TEXT,receipt_key TEXT,body_hash TEXT, PRIMARY KEY(batch_id,receipt_key));
      CREATE TABLE workmanship_sim_cache_assembly_preparations(batch_id TEXT PRIMARY KEY,preparation_hash TEXT,preparation_json TEXT);
      CREATE TABLE workmanship_sim_cache_assembly_preparation_chunks(batch_id TEXT,chunk_index INTEGER,chunk_text TEXT,PRIMARY KEY(batch_id,chunk_index));
      CREATE TABLE workmanship_sim_cloud_cache_versions(tenant_gid TEXT,project_gid TEXT,phase TEXT,next_version INTEGER, PRIMARY KEY(tenant_gid,project_gid,phase));
    ''')
    conn.close()
    @contextmanager
    def connect():
        raw = sqlite3.connect(path)
        raw.create_function('CHAR_LENGTH',1,len)
        raw.create_function('CONCAT',2,lambda a,b:a+b)
        raw.row_factory = sqlite3.Row
        class Connection:
            def cursor(self,*args,**kwargs): return Cursor(raw)
        try:
            yield Connection()
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally: raw.close()
    yield connect
    path.unlink()


SELECTOR = dict(endpoint_id='tc',object_uid='rev-1',object_kind='ItemRevision',revision_rule_uid='rule-1')


def create(repo):
    return repo.create(tenant_gid='2',actor_gid='1',project_gid='3',project_name='Project',phase='P1',display_name='V1',source_selector=SELECTOR,request_key='create-1')


def node(key, path, **extra):
    if not path and key!='root':path=[{'occurrence_uid':key,'item_revision_uid':'r1'}]
    return dict(occurrence_id=key,parent_occurrence_id=None if key=='root' else 'root',occurrence_path=path,has_children=False,**extra)


def page(batch, cursor=0, next_cursor=None, generation='a'*32, nodes=None):
    return dict(source_identity_hash=batch['source_hash'],generation=generation,cursor=cursor,next_cursor=next_cursor,child_count=cursor+len(nodes or [])+(1 if next_cursor is not None else 0),complete=False,parent=node('root',[]),nodes=nodes or [],captured_at='2026-09-28T00:00:00Z',cache_hit=False)


def test_restart_replay_and_all_fields(store):
    repo = CloudModelCacheRepository(store)
    batch = create(repo)
    task = repo.next_task(batch['batch_id'], '2')
    first = page(batch,next_cursor=1,nodes=[node('n1',[{'occurrence_uid':'o1','revision_uid':'r1'}],unknown={'zero':0,'flag':False,'null':None,'empty':''})])
    repo.apply_result(batch['batch_id'],'2',task,first)
    restarted = CloudModelCacheRepository(store)
    assert restarted.apply_result(batch['batch_id'],'2',task,first) is False
    task2 = restarted.next_task(batch['batch_id'],'2')
    assert task2['payload']['generation'] == 'a'*32
    assert task2['payload']['cursor'] == 1
    restarted.apply_result(batch['batch_id'],'2',task2,page(batch,cursor=1,nodes=[node('n2',[])]))
    result = restarted.query(batch['batch_id'],'2',search='zero',filters=[],mode='and',cursor=0,page_size=100)
    assert result['total'] == 1
    assert json.loads(result['rows'][0]['data_json'])['structure']['unknown'] == {'zero':0,'flag':False,'null':None,'empty':''}
    assert '/structure/unknown/flag' in result['fields']


def test_tree_order_is_parent_first_with_tc_sibling_order_across_pages_and_filters(store):
    repo=CloudModelCacheRepository(store);batch=create(repo);bid=batch['batch_id']
    parent={**node('z-parent',[],child_order=0,name='match parent'),'has_children':True}
    sibling=node('a-sibling',[],child_order=1,name='match sibling')
    first=page(batch,nodes=[parent,sibling]);first['parent']['has_children']=True
    repo.apply_result(bid,'2',repo.next_task(bid,'2'),first)
    task=repo.next_task(bid,'2')
    assert task['kind']=='children','structure tasks must precede queued properties'
    grandchild={**node('m-grandchild',parent['occurrence_path']+[{'occurrence_uid':'g','item_revision_uid':'r1'}],child_order=0,name='match child'),'parent_occurrence_id':'z-parent'}
    second=page(batch,nodes=[grandchild]);second['parent']=parent
    repo.apply_result(bid,'2',task,second)
    assert repo.next_task(bid,'2')['kind']=='properties','properties begin after every structure task completes'
    keys=lambda result:[row['node_key'] for row in result['rows']]
    first_page=repo.query(bid,'2',page_size=2)
    assert keys(first_page)==['root','z-parent']
    assert keys(repo.query(bid,'2',cursor=first_page['next_cursor'],page_size=2))==['m-grandchild','a-sibling']
    filtered=repo.query(bid,'2',search='match',page_size=2)
    assert filtered['total']==3
    assert keys(filtered)==['z-parent','m-grandchild']
    assert keys(repo.query(bid,'2',search='match',cursor=filtered['next_cursor'],page_size=2))==['a-sibling']


def test_generation_mismatch_rolls_back_page(store):
    repo = CloudModelCacheRepository(store)
    batch=create(repo); task=repo.next_task(batch['batch_id'],'2')
    repo.apply_result(batch['batch_id'],'2',task,page(batch,next_cursor=1,nodes=[node('n1',[])]))
    task=repo.next_task(batch['batch_id'],'2')
    with pytest.raises(CacheError,match='cache_generation_stale'):
        repo.apply_result(batch['batch_id'],'2',task,page(batch,cursor=1,generation='b'*32,nodes=[node('bad',[])]))
    assert repo.query(batch['batch_id'],'2',search='bad',filters=[],mode='and',cursor=0,page_size=100)['total'] == 0


def test_whole_batch_filter_null_false_and_tenant(store):
    repo=CloudModelCacheRepository(store); batch=create(repo); task=repo.next_task(batch['batch_id'],'2')
    repo.apply_result(batch['batch_id'],'2',task,page(batch,nodes=[node(str(i),[],value=i,flag=False) for i in range(20)]))
    result=repo.query(batch['batch_id'],'2',search='',filters=[{'field':'/structure/value','op':'eq','value_json':'19'}],mode='and',cursor=0,page_size=2)
    assert result['total']==1 and json.loads(result['rows'][0]['data_json'])['structure']['value']==19
    with pytest.raises(CacheError,match='cache_not_found'): repo.get(batch['batch_id'],'other')


def test_pause_version_and_create_idempotency(store):
    repo=CloudModelCacheRepository(store); batch=create(repo)
    assert create(repo)['batch_id']==batch['batch_id']
    repo.control(batch['batch_id'],'2','pause',batch['row_version'])
    assert repo.next_task(batch['batch_id'],'2') is None
    with pytest.raises(CacheError,match='cache_version_conflict'):
        repo.control(batch['batch_id'],'2','resume',batch['row_version'])
    updated=repo.get(batch['batch_id'],'2')
    assert repo.control(batch['batch_id'],'2','resume',updated['row_version'])['status']=='queued'


def test_provider_rejects_member_trigger_and_wrong_actor(store):
    from types import SimpleNamespace
    from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityBusinessError
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import CloudModelCacheProvider
    provider=CloudModelCacheProvider(CloudModelCacheRepository(store),SimpleNamespace())
    member=CapabilityContext(user_gid='1',team_gid='2',active_roles=('member',))
    with pytest.raises(CapabilityBusinessError,match='cache_trigger_forbidden'):
        asyncio.run(provider.create({},member))
    batch=create(provider.repo)
    other=CapabilityContext(user_gid='9',team_gid='2',active_roles=('super_admin',))
    with pytest.raises(CapabilityBusinessError,match='cache_actor_mismatch'):
        provider.advance({'batch_id':batch['batch_id']},other)


def test_worker_scope_is_explicit_and_cannot_be_used_by_other_workers(monkeypatch):
    from types import SimpleNamespace
    from backend.routers import deps
    monkeypatch.setattr(deps,'build_profile',lambda *args,**kwargs:dict(org_role='super_admin',permissions=['simulation.use'],grants=[]))
    identity=SimpleNamespace(consumer=SimpleNamespace(consumer_id='simulation.model_cache.worker'),actor=SimpleNamespace(user_id='1',authentication_method='durable_cache_trigger'))
    grants=deps.build_capability_authorization_grants({'gid':'1','system_role':'super_admin'},'2','worker',identity)
    assert grants.capability_scopes==('simulation.model_cache.advance',)
    identity.consumer.consumer_id='other.worker'
    assert deps.build_capability_authorization_grants({'gid':'1','system_role':'super_admin'},'2','worker',identity).capability_scopes==()


def test_connector_dispatch_reuses_admitted_plan_after_restart_and_completes(store):
    from types import SimpleNamespace
    from datetime import datetime, UTC
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import CloudModelCacheProvider
    from plugins.simulation.simulation_backend.capabilities.connector_contracts import TC_VISUALIZATION_SOURCE_SELECTOR
    import jsonschema
    repo=CloudModelCacheRepository(store)
    selector=dict(endpoint_id='tc-production',object_uid='root',item_revision_uid='',bom_view_uid='',revision_rule='Latest Working',configuration_date='2026-09-28T00:00:00Z')
    batch=repo.create(tenant_gid='2',actor_gid='1',project_gid='3',project_name='P',phase='A',display_name='V1',source_selector=selector,request_key='restart')
    plans={};queued=[]
    runtime=SimpleNamespace(bound_runtime_for_user=lambda *a:dict(runtime_type='electron',device_id='device-1'),get_plan_result=lambda plan_id,*a:plans.get(plan_id))
    def queue(plan,context,**kwargs):
        queued.append(plan);result=page(batch)
        if plan['steps'][0]['payload']['kind']=='properties':result=dict(source_identity_hash=batch['source_hash'],captured_at='2026-09-28T00:00:00Z',cache_hit=True,properties=dict(name='Root',weight_raw='0'),raw_fields=[])
        assert plan['steps'][0]['side_effect_classification']=='read'
        assert plan['steps'][0]['timeout_seconds']==600
        assert plan['capability_id']=='simulation.model_cache.advance'
        plans[plan['plan_id']]=dict(status='completed',outcome={'steps':[{'result':{'principal_hash':'sha256:'+'c'*64,'result_json':json.dumps(result)}}]})
        return SimpleNamespace(operation_id=plan['plan_id'])
    control=SimpleNamespace(repository=runtime,queue_v2=queue,clock=lambda:datetime.now(UTC))
    ctx=CapabilityContext(user_gid='1',team_gid='2',source='worker',active_roles=('super_admin',),capability_version_gid='cv2_'+'a'*24,business_definition_hash='sha256:'+'a'*64,catalog_release='rel_test',normalized_input_hash='sha256:'+'b'*64)
    provider=CloudModelCacheProvider(repo,control)
    # Simulate crash after connector admission but before operation ID commit.
    class Crash(BaseException): pass
    real_queue=control.queue_v2
    def crash(plan,context,**kwargs): real_queue(plan,context,**kwargs);raise Crash()
    control.queue_v2=crash
    with pytest.raises(Crash):provider.advance({'batch_id':batch['batch_id']},ctx)
    control.queue_v2=real_queue
    restarted=CloudModelCacheProvider(CloudModelCacheRepository(store),control)
    restarted.advance({'batch_id':batch['batch_id']},ctx)
    assert len(queued)==1
    completed=restarted.advance({'batch_id':batch['batch_id']},ctx).data
    assert completed['status']=='completed' and len(queued)==2
    jsonschema.validate(completed['source_selector'],TC_VISUALIZATION_SOURCE_SELECTOR)


def test_principal_change_rolls_back(store):
    repo=CloudModelCacheRepository(store); batch=create(repo)
    task=repo.next_task(batch['batch_id'],'2')
    repo.apply_result(batch['batch_id'],'2',task,page(batch),'sha256:'+'a'*64)
    prop=repo.next_task(batch['batch_id'],'2')
    with pytest.raises(CacheError,match='cache_principal_changed'):
        repo.apply_result(batch['batch_id'],'2',prop,dict(source_identity_hash=batch['source_hash'],properties={}), 'sha256:'+'b'*64)
    assert repo.get(batch['batch_id'],'2')['status']!='completed'
    assert repo.next_task(batch['batch_id'],'2')['task_key']==prop['task_key']


def test_late_attempt_cannot_commit_or_fail_new_attempt(store):
    repo=CloudModelCacheRepository(store); batch=create(repo)
    old=repo.dispatch(batch['batch_id'],'2',lambda *_:'op-0')
    repo.failure(batch['batch_id'],'2','connector_offline',old)
    new=repo.dispatch(batch['batch_id'],'2',lambda *_:'op-1')
    assert new['attempt']==1
    assert repo.apply_result(batch['batch_id'],'2',old,page(batch)) is False
    repo.failure(batch['batch_id'],'2','teamcenter_worker_failed',old)
    assert repo.get(batch['batch_id'],'2')['status']=='running'
    assert repo.next_task(batch['batch_id'],'2')['operation_id']=='op-1'


def test_incomplete_and_duplicate_pages_cannot_publish(store):
    repo=CloudModelCacheRepository(store); batch=create(repo); task=repo.next_task(batch['batch_id'],'2')
    malformed=page(batch,nodes=[node('x',[])])
    malformed['child_count']=2
    with pytest.raises(CacheError,match='cache_page_invalid'):repo.apply_result(batch['batch_id'],'2',task,malformed)
    assert repo.get(batch['batch_id'],'2')['node_count']==0
    first=page(batch,next_cursor=1,nodes=[node('x',[])])
    first['parent']['has_children']=True
    repo.apply_result(batch['batch_id'],'2',task,first)
    next_task=repo.next_task(batch['batch_id'],'2')
    with pytest.raises(CacheError,match='cache_page_invalid'):
        repo.apply_result(batch['batch_id'],'2',next_task,page(batch,cursor=1,nodes=[node('x',[])]))
    assert repo.get(batch['batch_id'],'2')['node_count']==2


def test_project_validation_uses_governed_owner_and_canonical_name(store):
    from backend.capability_v2.provider_contracts import CapabilityContext,CapabilityBusinessError
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import CloudModelCacheProvider
    ctx=CapabilityContext(user_gid='1',team_gid='2',active_roles=('super_admin',),idempotency_key='create-project')
    async def project(gid,context):return {'data':{'success':True,'data':dict(gid=gid,team_id='2',name='Authoritative',is_deleted=0)}}
    provider=CloudModelCacheProvider(CloudModelCacheRepository(store),project_reader=project)
    payload=dict(project_gid='3',project_name='Spoofed',phase='P1',display_name='V1',source_selector=SELECTOR,trigger_kind='manual')
    assert asyncio.run(provider.create(payload,ctx)).data['project_name']=='Authoritative'
    async def foreign(*_):return dict(gid='3',team_id='99',name='Foreign')
    provider.project_reader=foreign
    with pytest.raises(CapabilityBusinessError,match='current tenant'):asyncio.run(provider.create(payload,ctx))


def test_typed_numeric_empty_and_project_scope_filter(store):
    from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import matches
    assert matches({'value':0},[dict(field='/value',op='gte',value_json='0')],'and')
    assert not matches({'value':False},[dict(field='/value',op='gte',value_json='0')],'and')
    assert not matches({},[dict(field='/absent',op='not_empty',value_json='null')],'and')
    repo=CloudModelCacheRepository(store); create(repo)
    assert len(repo.list('2',{'3'}))==1
    assert repo.list('2',set())==repo.list('2',{'99'})==[]


def test_catalog_budget_and_byte_paging_keep_large_values_readable(store):
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import specs
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
    descriptor=next(descriptor_for(spec) for spec,_ in specs() if spec.id.endswith('model_cache.query'))
    assert descriptor.execution_budget.max_output_bytes==32*1024*1024
    assert descriptor.timeout_seconds==300
    repo=CloudModelCacheRepository(store);batch=create(repo);task=repo.next_task(batch['batch_id'],'2')
    value='x'*(2*1024*1024)
    data=page(batch,nodes=[node('n'+str(i),[],value=value) for i in range(3)])
    data['parent']['has_children']=True
    repo.apply_result(batch['batch_id'],'2',task,data)
    rows=[];cursor=0
    while cursor is not None:
        result=repo.query(batch['batch_id'],'2',page_size=500,cursor=cursor)
        assert result['rows']
        rows.extend(result['rows']);cursor=result['next_cursor']
    assert len(rows)==4
    assert all(json.loads(row['data_json'])['structure']['value']==value for row in rows if row['node_key']!='root')


def test_versions_are_server_allocated_per_project_stage_and_replays_do_not_increment(store):
    repo=CloudModelCacheRepository(store)
    first=create(repo)
    assert first['display_name']=='v1' and create(repo)['display_name']=='v1'
    renamed=repo.create(tenant_gid='2',actor_gid='1',project_gid='3',project_name='Renamed project',phase='P1',source_selector=SELECTOR,request_key='create-1')
    assert renamed['batch_id']==first['batch_id'] and renamed['project_name']=='Project'
    args=dict(tenant_gid='2',actor_gid='9',project_gid='3',project_name='Project',phase='P1',source_selector=SELECTOR,request_key='another')
    assert repo.create(**args)['display_name']=='v2'
    assert repo.create(**{**args,'phase':'TG0','request_key':'new-stage'})['display_name']=='v1'
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import specs,DATA_STAGES
    schema=next(spec.input_schema for spec,_ in specs() if spec.id.endswith('model_cache.create'))
    assert 'display_name' not in schema['properties']
    assert schema['properties']['phase']['enum']==list(DATA_STAGES)


@pytest.mark.parametrize('fails',[False,True])
def test_simulation_connections_explicitly_begin_then_commit_or_rollback(monkeypatch,fails):
    from types import SimpleNamespace
    from plugins.simulation.simulation_backend.data import connection
    events=[]
    raw=SimpleNamespace(begin=lambda:events.append('begin'),commit=lambda:events.append('commit'),rollback=lambda:events.append('rollback'),close=lambda:events.append('close'))
    monkeypatch.setattr(connection,'_get_pool',lambda:SimpleNamespace(connection=lambda:raw))
    monkeypatch.setattr(connection,'wrap_connection',lambda value:value)
    def run():
        with connection.get_simulation_conn() as conn:
            assert conn is raw and events==['begin']
            if fails:raise RuntimeError('abort')
    if fails:
        with pytest.raises(RuntimeError,match='abort'):run()
    else:run()
    assert events==['begin','rollback' if fails else 'commit','close']


def test_gateway_simulation_transaction_begins_and_cleans_up_a_begin_failure(monkeypatch):
    from types import SimpleNamespace
    from plugins.simulation.simulation_backend.data import connection
    events=[]
    raw=SimpleNamespace(begin=lambda:events.append('begin'),close=lambda:events.append('close'))
    monkeypatch.setattr(connection,'_get_pool',lambda:SimpleNamespace(connection=lambda:raw))
    monkeypatch.setattr(connection,'wrap_connection',lambda value:value)
    assert connection.open_simulation_transaction() is raw and events==['begin']
    def abort():raise RuntimeError('begin unavailable')
    raw.begin=abort
    with pytest.raises(RuntimeError,match='begin unavailable'):connection.open_simulation_transaction()
    assert events==['begin','close']


def test_resolve_visualization_node_reads_one_completed_cache_identity(store):
    repo=CloudModelCacheRepository(store);batch=create(repo)
    data={'structure':{'occurrence_id':'occ-1','item_revision_uid':'rev-node'}}
    with store() as conn,conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s WHERE batch_id=%s',('completed',batch['batch_id']))
        cur.execute('INSERT INTO workmanship_sim_cloud_cache_nodes(batch_id,node_key,data_json) VALUES(%s,%s,%s)',
            (batch['batch_id'],'occ-1',json.dumps(data)))
    resolved=repo.resolve_visualization_node(batch['batch_id'],'2','occ-1')
    assert resolved['project_gid']=='3'
    assert resolved['item_revision_uid']=='rev-node'
    assert resolved['source_selector']==SELECTOR


def test_resolve_visualization_node_fails_closed_for_state_node_and_identity(store):
    repo=CloudModelCacheRepository(store);batch=create(repo)
    with pytest.raises(CacheError,match='cache_source_not_ready'):
        repo.resolve_visualization_node(batch['batch_id'],'2','missing')
    with store() as conn,conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s WHERE batch_id=%s',('completed',batch['batch_id']))
    with pytest.raises(CacheError,match='cache_source_node_not_found'):
        repo.resolve_visualization_node(batch['batch_id'],'2','missing')
    with store() as conn,conn.cursor() as cur:
        cur.execute('INSERT INTO workmanship_sim_cloud_cache_nodes(batch_id,node_key,data_json) VALUES(%s,%s,%s)',
            (batch['batch_id'],'occ-1',json.dumps({'structure':{'occurrence_id':'occ-1'}})))
    with pytest.raises(CacheError,match='cache_source_identity_missing'):
        repo.resolve_visualization_node(batch['batch_id'],'2','occ-1')
    with store() as conn,conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_cloud_cache_nodes SET data_json=%s WHERE batch_id=%s AND node_key=%s',
            (json.dumps({'structure':{'occurrence_id':'other','item_revision_uid':'rev'}}),batch['batch_id'],'occ-1'))
    with pytest.raises(CacheError,match='cache_source_stale'):
        repo.resolve_visualization_node(batch['batch_id'],'2','occ-1')
