import json
import pytest
from plugins.simulation.tests.test_cloud_model_cache import store, create, Cursor
from plugins.simulation.tests.test_cloud_model_cache_bulk import snapshot_page, PRINCIPAL
from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CloudModelCacheRepository, CacheError


def completed(store, count=5):
    repo=CloudModelCacheRepository(store)
    batch=repo.create(tenant_gid='2',actor_gid='1',project_gid='3',project_name='Project',phase='SOP',request_key='pinned-create',source_selector={'endpoint_id':'tc-production','object_uid':'root','item_revision_uid':'revision','bom_view_uid':'','revision_rule':'Latest Working','configuration_date':'2026-09-28T00:00:00Z'})
    for cursor in range(0,count,500):
        task=repo.dispatch(batch['batch_id'],'2',lambda b,t:'pinned-'+t['task_key'],snapshot=True)
        repo.apply_snapshot_result(batch['batch_id'],'2',task,snapshot_page(batch,cursor,count=count,size=500),PRINCIPAL)
    return repo,batch


def test_roots_manifest_and_lazy_properties_preserve_fixed_identity(store):
    repo,batch=completed(store)
    result=repo.query_pinned(batch['batch_id'],'2',scope='roots')
    assert [n['node_key'] for n in result['nodes']]==['root']
    root=result['nodes'][0]
    assert root['parent_occurrence_id'] is None and root['has_children'] is True
    assert 'properties_result' not in root
    identity=result['identity']; manifest=result['manifest']
    assert identity['generation']=='a'*32 and identity['snapshot_hash'].startswith('sha256:')
    assert identity['snapshot_hash']!=batch['source_hash']
    assert manifest['capture_started_at'] is None
    assert manifest['snapshot_hash_algorithm']=='ai00.cache.snapshot.canonical-lines.v1'
    assert manifest['readiness']['geometry_files']=='not_requested'
    assert manifest['spatial_semantics']['status']=='unverified'
    detail=repo.query_pinned(batch['batch_id'],'2',scope='node',node_key='node-1',projection='properties',expected_generation=identity['generation'],expected_snapshot_hash=identity['snapshot_hash'])
    assert len(detail['nodes'])==1
    assert detail['nodes'][0]['parent_occurrence_id']=='root'
    assert detail['nodes'][0]['properties_result']['properties']['torque_raw']=='12'
    assert detail['nodes'][0]['geometry_refs']==[]
    assert detail['identity']==identity
    assert repo.query_pinned(batch['batch_id'],'2',scope='batch')['nodes'][0]['node_key']=='root'


def test_children_keyset_is_bound_and_does_not_rescan_tree_after_manifest(store,monkeypatch):
    repo,batch=completed(store)
    first=repo.query_pinned(batch['batch_id'],'2',scope='children',node_key='root',page_size=2)
    assert [n['node_key'] for n in first['nodes']]==['node-1','node-2']
    assert isinstance(first['next_cursor'],str)
    calls=[]; execute=Cursor.execute
    def counted(self,sql,params=()):calls.append(sql);return execute(self,sql,params)
    monkeypatch.setattr(Cursor,'execute',counted)
    second=repo.query_pinned(batch['batch_id'],'2',scope='children',node_key='root',page_size=2,cursor=first['next_cursor'])
    assert [n['node_key'] for n in second['nodes']]==['node-3','node-4']
    assert second['next_cursor'] is None
    assert not any('ORDER BY snapshot_position' in sql for sql in calls)
    with pytest.raises(CacheError,match='cache_cursor_invalid'):
        repo.query_pinned(batch['batch_id'],'2',scope='roots',cursor=first['next_cursor'])
    with pytest.raises(CacheError,match='cache_cursor_invalid'):
        repo.query_pinned(batch['batch_id'],'2',scope='children',node_key='root',projection='properties',cursor=first['next_cursor'])


def test_unready_missing_and_mismatched_snapshots_fail_explicitly(store):
    repo=CloudModelCacheRepository(store); batch=create(repo)
    with pytest.raises(CacheError,match='cache_snapshot_not_ready'):repo.query_pinned(batch['batch_id'],'2',scope='roots')
    task=repo.dispatch(batch['batch_id'],'2',lambda *_:'pinned-op',snapshot=True)
    repo.apply_snapshot_result(batch['batch_id'],'2',task,snapshot_page(batch,0,count=1),PRINCIPAL)
    with pytest.raises(CacheError,match='cache_generation_stale'):repo.query_pinned(batch['batch_id'],'2',expected_generation='d'*32)
    with pytest.raises(CacheError,match='cache_snapshot_mismatch'):repo.query_pinned(batch['batch_id'],'2',expected_snapshot_hash='sha256:'+'0'*64)
    with pytest.raises(CacheError,match='cache_node_not_found'):repo.query_pinned(batch['batch_id'],'2',scope='node',node_key='missing')
    with pytest.raises(CacheError,match='cache_not_found'):repo.query_pinned(batch['batch_id'],'other')


def test_query_v2_is_registered_and_v1_remains_unchanged(store):
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import specs
    versions={spec.version:spec for spec,_ in specs() if spec.id=='simulation.model_cache.query'}
    assert set(versions)=={1,2}
    assert versions[1].input_schema['properties']['cursor']['type']=='integer'
    assert versions[2].input_schema['properties']['scope']['enum']==['roots','batch','children','node']
    assert versions[2].input_schema['properties']['cursor']['type']==['string','null']


def test_cold_old_snapshot_roots_never_scan_full_properties_or_compute_hash(store,monkeypatch):
    repo,batch=completed(store, count=16750)
    with store() as conn,conn.cursor() as cur:cur.execute('DELETE FROM workmanship_sim_cloud_cache_manifests')
    calls=[];execute=Cursor.execute
    def counted(self,sql,params=()):calls.append(sql);return execute(self,sql,params)
    monkeypatch.setattr(Cursor,'execute',counted)
    result=repo.query_pinned(batch['batch_id'],'2',scope='roots')
    assert len(result['nodes'])==1
    assert result['identity']['snapshot_hash'] is None
    assert result['manifest']['hash_status']=='unavailable'
    assert not any('SELECT node_key,data_json' in sql and 'LIMIT' not in sql for sql in calls)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies=list(pool.map(lambda _:repo.query_pinned(batch['batch_id'],'2',scope='roots'),range(4)))
    assert all(len(reply['nodes'])==1 and reply['identity']==result['identity'] for reply in replies)
    with pytest.raises(CacheError,match='cache_snapshot_hash_unavailable'):
        repo.query_pinned(batch['batch_id'],'2',expected_snapshot_hash='sha256:'+'0'*64)


def test_closed_contract_matches_real_provider_response_and_project_permissions(store,monkeypatch):
    from types import SimpleNamespace
    from jsonschema import validate
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import CloudModelCacheProvider,specs
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    repo,batch=completed(store)
    provider=CloudModelCacheProvider(repository=repo)
    context=SimpleNamespace(user_gid='1',team_gid='2',active_roles=('super_admin',))
    response=provider.query_pinned({'batch_id':batch['batch_id']},context).data
    spec=next(s for s,_ in specs(provider) if s.id=='simulation.model_cache.query' and s.version==2)
    validate(response,spec.output_schema)
    from backend.capabilities.validation_next import validate_payload
    detail=provider.query_pinned({'batch_id':batch['batch_id'],'scope':'node','node_key':'node-1','projection':'properties'},context).data
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for,governed_spec
    descriptor=descriptor_for(governed_spec(spec))
    validate_payload(dict(descriptor.output_schema),detail,label='output')
    monkeypatch.setattr('plugins.simulation.simulation_backend.capabilities.cloud_model_cache.can_manage_project',lambda *_:False)
    with pytest.raises(CapabilityBusinessError,match='cache_project_forbidden'):
        provider.query_pinned({'batch_id':batch['batch_id']},SimpleNamespace(user_gid='other',team_gid='2',active_roles=()))


@pytest.mark.parametrize('size',[2200000,5000000])
def test_large_raw_fields_and_legacy_page_use_bounded_streaming_query(store,monkeypatch,size):
    from backend.capabilities.validation_next import validate_payload
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import specs
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for,governed_spec
    repo,batch=completed(store,count=1)
    with store() as conn,conn.cursor() as cur:
        cur.execute('SELECT data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s',(batch['batch_id'],))
        row=json.loads(cur.fetchone()['data_json'])
        row['page'].update(source_identity_hash=batch['source_hash'],generation='a'*32,cursor=0,next_cursor=None,complete=False,captured_at='2026-09-28T00:00:00Z',cache_hit=True)
        row['properties_result']['raw_fields'].append({'object_uid':'shared-rev','object_kind':'ItemRevision','field':'large_field','read_state':'value','value_json':json.dumps('x'*size)})
        cur.execute('UPDATE workmanship_sim_cloud_cache_nodes SET data_json=%s WHERE batch_id=%s',(json.dumps(row),batch['batch_id']))
        cur.execute('DELETE FROM workmanship_sim_cloud_cache_manifests')
    def no_fetchall(*_):raise AssertionError('Property rows must stream before byte truncation')
    monkeypatch.setattr(Cursor,'fetchall',no_fetchall)
    descriptor=descriptor_for(governed_spec(next(s for s,_ in specs() if s.id=='simulation.model_cache.query' and s.version==2)))
    response=repo.query_pinned(batch['batch_id'],'2',scope='node',node_key='root',projection='raw')
    validate_payload(dict(descriptor.output_schema),response,label='output')
    assert response['nodes'][0]['raw_snapshot']['properties_result']['raw_fields'][-1]['value_json']==row['properties_result']['raw_fields'][-1]['value_json']
