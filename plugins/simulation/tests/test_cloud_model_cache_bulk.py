"""Actual SQLite repository checkpoints for bounded complete snapshot rows."""
import json
import pytest

from plugins.simulation.tests.test_cloud_model_cache import store,create
from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CloudModelCacheRepository,CacheError

PRINCIPAL='sha256:'+'c'*64

def test_snapshot_page_batches_existing_row_lookup_and_new_row_inserts(store,monkeypatch):
    from plugins.simulation.tests.test_cloud_model_cache import Cursor
    repo=CloudModelCacheRepository(store);batch=create(repo)
    task=repo.dispatch(batch['batch_id'],'2',lambda *_:'bulk-op',snapshot=True)
    calls=[];batches=[];execute=Cursor.execute;executemany=Cursor.executemany
    def counted(self,sql,params=()):calls.append(sql);return execute(self,sql,params)
    def grouped(self,sql,params):
        params=list(params);batches.append((sql,len(params)));return executemany(self,sql,params)
    monkeypatch.setattr(Cursor,'execute',counted);monkeypatch.setattr(Cursor,'executemany',grouped)
    assert repo.apply_snapshot_result(batch['batch_id'],'2',task,snapshot_page(batch,0,count=1000),PRINCIPAL)
    reads=[sql for sql in calls if sql.startswith('SELECT') and 'workmanship_sim_cloud_cache_nodes' in sql]
    assert len(reads)==1,'one network lookup per page, not one per node'
    assert [count for sql,count in batches if sql.startswith('INSERT INTO workmanship_sim_cloud_cache_nodes')]==[200]
    assert len(calls)<20

def snapshot_page(batch,cursor,count=10000,size=200,generation='a'*32):
    rows=[]
    for index in range(cursor,min(count,cursor+size)):
        key='root' if index==0 else f'node-{index}'
        path=[] if index==0 else [{'occurrence_uid':f'O-{index}','item_revision_uid':'shared-rev'}]
        rows.append({'structure':dict(occurrence_id=key,parent_occurrence_id=None if index==0 else 'root',occurrence_path=path,depth=0 if index==0 else 1,child_order=0 if index==0 else index-1,name=key,item_revision_uid='shared-rev',revision_id='00',component_type='Part',has_children=index==0 and count>1),
                     'page':{'child_count':count-1 if index==0 else 0},
                     'properties_result':dict(source_identity_hash=batch['source_hash'],captured_at='2026-09-28T00:00:00Z',cache_hit=False,properties={'name':key,'owning_user':'owner','torque_raw':'12'},raw_fields=[dict(object_uid='shared-rev',object_kind='ItemRevision',field='IMAN_Rendering',read_state='value',value_json='[]')])})
    next_cursor=cursor+len(rows)
    return dict(source_identity_hash=batch['source_hash'],captured_at='2026-09-28T00:00:00Z',generation=generation,structure_hash='sha256:'+'b'*64,node_count=count,cursor=cursor,next_cursor=next_cursor if next_cursor<count else None,complete=next_cursor==count,rows=rows)

def test_ten_thousand_nodes_use_twenty_durable_pages_and_resume_without_duplicate_rows(store):
    repo=CloudModelCacheRepository(store);batch=create(repo);queued=[]
    def queue(batch,task):queued.append(task['task_key']);return {'device_id':'device','operation_id':'op-'+task['task_key']}
    for cursor in range(0,10000,500):
        task=repo.dispatch(batch['batch_id'],'2',queue,snapshot=True)
        assert task['kind']=='snapshot' and task['payload']['cursor']==cursor
        assert task['payload']['page_size']==500
        result=snapshot_page(batch,cursor,size=500)
        assert repo.apply_snapshot_result(batch['batch_id'],'2',task,result,PRINCIPAL)
        restarted=CloudModelCacheRepository(store)
        assert restarted.apply_snapshot_result(batch['batch_id'],'2',task,result,PRINCIPAL) is False
        repo=restarted
    assert len(queued)==20
    done=repo.get(batch['batch_id'],'2');assert done['status']=='completed' and done['node_count']==10000
    with store() as conn,conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_receipts');assert cur.fetchone()['count']==20
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_tasks WHERE kind='properties'");assert cur.fetchone()['count']==0
    rows=repo.query(batch['batch_id'],'2',cursor=0,page_size=2)['rows'];assert rows[0]['node_key']=='root'
    assert json.loads(rows[1]['data_json'])['properties_result']['properties']['torque_raw']=='12'

def test_snapshot_upgrade_settles_an_admitted_legacy_plan_and_preserves_its_receipt(store):
    from plugins.simulation.tests.test_cloud_model_cache import page
    repo=CloudModelCacheRepository(store);batch=create(repo)
    legacy=repo.dispatch(batch['batch_id'],'2',lambda *_:{'device_id':'device','operation_id':'old-op'})
    settling=repo.dispatch(batch['batch_id'],'2',lambda *_:pytest.fail('must not queue competing snapshot'),snapshot=True)
    assert settling['operation_id']=='old-op'
    repo.apply_result(batch['batch_id'],'2',legacy,page(batch),PRINCIPAL)
    task=repo.dispatch(batch['batch_id'],'2',lambda *_:{'device_id':'device','operation_id':'new-op'},snapshot=True)
    assert task['kind']=='snapshot'
    assert repo.apply_snapshot_result(batch['batch_id'],'2',task,snapshot_page(batch,0,count=1),PRINCIPAL)
    assert repo.get(batch['batch_id'],'2')['status']=='completed'
    with store() as conn,conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_receipts');assert cur.fetchone()['count']==2
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_tasks WHERE status='superseded'");assert cur.fetchone()['count']==1

def test_rejected_continuation_rolls_back_and_never_publishes_mixed_generations(store):
    repo=CloudModelCacheRepository(store);batch=create(repo);queue=lambda b,t:{'device_id':'device','operation_id':'op-'+t['task_key']}
    first=repo.dispatch(batch['batch_id'],'2',queue,snapshot=True);repo.apply_snapshot_result(batch['batch_id'],'2',first,snapshot_page(batch,0,count=3,size=2),PRINCIPAL)
    next_task=repo.dispatch(batch['batch_id'],'2',queue,snapshot=True)
    with pytest.raises(CacheError,match='cache_generation_stale'):
        repo.apply_snapshot_result(batch['batch_id'],'2',next_task,snapshot_page(batch,2,count=3,generation='d'*32),PRINCIPAL)
    assert repo.get(batch['batch_id'],'2')['node_count']==2
    repo.control(batch['batch_id'],'2','pause',repo.get(batch['batch_id'],'2')['row_version'])
    assert repo.apply_snapshot_result(batch['batch_id'],'2',next_task,snapshot_page(batch,2,count=3),PRINCIPAL) is False
    assert repo.dispatch(batch['batch_id'],'2',queue,snapshot=True) is None


def test_provider_selects_exact_advertised_v2_and_keeps_cloud_plan_version_one(store):
    from types import SimpleNamespace
    from datetime import datetime,UTC
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import CloudModelCacheProvider
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
    selector=dict(endpoint_id='tc-production',object_uid='root',item_revision_uid='',bom_view_uid='',revision_rule='Latest Working',configuration_date='2026-09-28T00:00:00Z')
    repo=CloudModelCacheRepository(store);batch=repo.create(tenant_gid='2',actor_gid='1',project_gid='3',project_name='P',phase='SOP',source_selector=selector,request_key='bulk-provider')
    operation,contract=DIRECT_VISMOCKUP_OPERATIONS['tc_cache_v2'];plans={};queued=[]
    health=dict(runtime_generation=7,runtime_instance_id='instance',adapter={'operations':[dict(operation_id=operation,contract_hash=contract)]})
    runtime=dict(runtime_type='electron',device_id='device',runtime_generation=7,current_runtime_instance_id='instance',adapter_health_json=json.dumps(health))
    repository=SimpleNamespace(bound_runtime_for_user=lambda *_:runtime,get_plan_result=lambda plan,*_:plans.get(plan))
    def queue(plan,context,**kwargs):
        queued.append(plan);step=plan['steps'][0]
        assert step['operation_id']==operation and step['contract_hash']==contract
        assert step['payload']==dict(source_selector=selector,batch_id=batch['batch_id'],cursor=0,page_size=500,generation=None,expected_principal_hash=None)
        assert step['side_effect_classification']=='read' and step['timeout_seconds']==600
        assert plan['capability_id']=='simulation.model_cache.advance' and plan['major_version']==1
        plans[plan['plan_id']]=dict(status='completed',outcome={'steps':[{'result':dict(principal_hash=PRINCIPAL,result_json=json.dumps(snapshot_page(batch,0,count=1)))}]})
        return SimpleNamespace(operation_id=plan['plan_id'])
    control=SimpleNamespace(repository=repository,queue_v2=queue,clock=lambda:datetime.now(UTC))
    ctx=CapabilityContext(user_gid='1',team_gid='2',source='worker',active_roles=('super_admin',),capability_version_gid='cv2_'+'a'*24,business_definition_hash='sha256:'+'a'*64,catalog_release='rel_test',normalized_input_hash='sha256:'+'b'*64)
    result=CloudModelCacheProvider(repo,control).advance({'batch_id':batch['batch_id']},ctx).data
    assert result['status']=='completed' and len(queued)==1


def test_legacy_rows_cannot_hide_a_duplicate_snapshot_identity_on_another_page(store):
    repo=CloudModelCacheRepository(store);batch=create(repo);bid=batch['batch_id']
    old=snapshot_page(batch,0,count=3)['rows'];old[2]['structure']['occurrence_id']='old'
    old[2]['structure']['occurrence_path'][0]['occurrence_uid']='OLD'
    with store() as conn,conn.cursor() as cur:
        for row in (old[0],old[2]):cur.execute('INSERT INTO workmanship_sim_cloud_cache_nodes(batch_id,node_key,data_json) VALUES(%s,%s,%s)',(bid,row['structure']['occurrence_id'],json.dumps(row)))
        cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET node_count=2 WHERE batch_id=%s',(bid,))
    queue=lambda b,t:'op-'+t['task_key']
    first=repo.dispatch(bid,'2',queue,snapshot=True);repo.apply_snapshot_result(bid,'2',first,snapshot_page(batch,0,count=3,size=2),PRINCIPAL)
    final=repo.dispatch(bid,'2',queue,snapshot=True);bad=snapshot_page(batch,2,count=3)
    bad['rows'][0]=snapshot_page(batch,1,count=3,size=1)['rows'][0]
    with pytest.raises(CacheError,match='cache_page_invalid'):repo.apply_snapshot_result(bid,'2',final,bad,PRINCIPAL)
    assert repo.get(bid,'2')['status']=='running'
