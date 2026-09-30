import pytest
import json
from types import SimpleNamespace
from plugins.simulation.tests.test_cloud_model_cache import store
from plugins.simulation.tests.test_cloud_model_cache_pinned import completed
from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CacheError


def test_member_validation_never_accepts_arbitrary_file_or_reads_current_revision(store):
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_files import member
    repo,batch=completed(store)
    with pytest.raises(CacheError,match='cache_file_not_referenced'):
        member(repo,batch['batch_id'],'2','node-1','dataset','arbitrary-file')


def test_result_artifact_media_is_derived_from_signed_operation():
    from backend.routers.simulation_connector import runtime_artifact_media
    assert runtime_artifact_media('vismockup.view.capture@1')=='image/png'
    assert runtime_artifact_media('teamcenter.model_file.fetch@1')=='model/jt'
    with pytest.raises(ValueError):runtime_artifact_media('vismockup.model.open@1')


@pytest.mark.parametrize('operation,size,allowed', [
    ('teamcenter.model_file.fetch@1',512*1024*1024,True),
    ('teamcenter.model_file.fetch@1',512*1024*1024+1,False),
    ('vismockup.view.capture@1',100*1024*1024,True),
    ('vismockup.view.capture@1',100*1024*1024+1,False),
])
def test_upload_limit_is_bound_to_signed_operation(monkeypatch,operation,size,allowed):
    import asyncio
    from fastapi import HTTPException
    from backend.routers import simulation_connector as route
    from backend.capability_v2 import artifacts
    step=SimpleNamespace(step_id='step',operation_id=operation,payload={'artifact_resource_refs':[]})
    plan=SimpleNamespace(steps=[step],actor_id='1',tenant_id='2')
    monkeypatch.setattr(route.runtime_session_service,'leased_plan',lambda **_:plan)
    monkeypatch.setattr(route,'ConnectorExecutionPlanV2',SimpleNamespace(model_validate=lambda value:value))
    reached=[]
    def storage():
        reached.append(True)
        raise RuntimeError('storage_boundary_reached')
    monkeypatch.setattr(artifacts,'configured_object_storage',storage)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(route.runtime_capture_artifact('plan','step',None,lease_id='lease',
            content_sha256='a'*64,content_length=size,pins={'device_id':'device'}))
    assert bool(reached)==allowed
    assert exc.value.detail['code']==('artifact_upload_failed' if allowed else 'artifact_integrity_failed')


def test_large_artifact_storage_does_not_block_other_async_requests(monkeypatch):
    import asyncio,threading,time
    from backend.routers import simulation_connector as route
    from backend.capability_v2 import artifacts
    step=SimpleNamespace(step_id='step',operation_id='teamcenter.model_file.fetch@1',payload={'artifact_resource_refs':[]})
    plan=SimpleNamespace(steps=[step],actor_id='1',tenant_id='2')
    monkeypatch.setattr(route.runtime_session_service,'leased_plan',lambda **_:plan)
    monkeypatch.setattr(route,'ConnectorExecutionPlanV2',SimpleNamespace(model_validate=lambda value:value))
    monkeypatch.setattr(artifacts,'configured_object_storage',lambda:None)
    main_thread=threading.get_ident();ticks=[]
    class Service:
        def __init__(self,*_):pass
        def create_upload(self,*_,**__):return SimpleNamespace(upload_id='upload')
        def upload_stream(self,upload,identity,stream):
            assert threading.get_ident()!=main_thread
            assert stream.read()==b'x'*24
            time.sleep(.08)
            assert ticks
        def finalize(self,*_,**__):
            assert threading.get_ident()!=main_thread
            return SimpleNamespace(model_dump=lambda **_:{'artifact_id':'artifact'})
    monkeypatch.setattr(artifacts,'ArtifactService',Service)
    class Request:
        async def stream(self):yield b'x'*24
    async def scenario():
        async def other_request():
            await asyncio.sleep(.01);ticks.append('responsive')
        result,_=await asyncio.gather(route.runtime_capture_artifact('plan','step',Request(),lease_id='lease',
            content_sha256='a'*64,content_length=24,pins={'device_id':'device'}),other_request())
        assert result['success']
    asyncio.run(scenario())


def file_snapshot(store):
    from plugins.simulation.tests.test_cloud_model_cache import create
    from plugins.simulation.tests.test_cloud_model_cache_bulk import snapshot_page,PRINCIPAL
    from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CloudModelCacheRepository
    repo=CloudModelCacheRepository(store);batch=create(repo)
    task=repo.dispatch(batch['batch_id'],'2',lambda *_:'file-snapshot',snapshot=True)
    page=snapshot_page(batch,0,count=1)
    ref={'dataset_uid':'dataset','file_uid':'file','file_name':'cached.jt','relation_type':'IMAN_Rendering'}
    page['rows'][0]['properties_result']['raw_fields'][0]['value_json']=json.dumps([ref])
    repo.apply_snapshot_result(batch['batch_id'],'2',task,page,PRINCIPAL)
    return repo,batch,ref


def test_known_reference_preserves_exact_snapshot_identity(store):
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_files import member
    repo,batch,ref=file_snapshot(store)
    identity,revision,actual=member(repo,batch['batch_id'],'2','root','dataset','file')
    assert actual==ref and revision=='shared-rev'
    assert identity['generation']=='a'*32
    assert identity['snapshot_hash'].startswith('sha256:')
    with pytest.raises(CacheError,match='cache_generation_stale'):
        member(repo,batch['batch_id'],'2','root','dataset','file',expected_generation='b'*32)


@pytest.mark.parametrize('mutation',['identity','file_ref','media','hash','length','plan_node','expected_hash'])
def test_result_rejects_cross_snapshot_or_unverified_artifact(store,mutation):
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_files import CacheFileProvider,member
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    repo,batch,ref=file_snapshot(store)
    identity,revision,_=member(repo,batch['batch_id'],'2','root','dataset','file')
    payload={'batch_id':batch['batch_id'],'node_key':'root','dataset_uid':'dataset','file_uid':'file','operation_id':'file-op'}
    admitted={**identity,'node_key':'root','item_revision_uid':revision,'file_ref':ref,'expected_content_hash':None}
    result={'identity':identity.copy(),'node_key':'root','item_revision_uid':revision,'file_ref':ref.copy(),'artifact_ref':{'artifact_id':'artifact-1','media_type':'model/jt','sha256':'c'*64,'byte_size':32,'version':1},'content_hash':'sha256:'+'c'*64,'byte_length':32,'acquired_at':'2026-09-28T00:00:00Z','captured_bytes_verified':False}
    if mutation=='identity':result['identity']['batch_id']='b'*32
    if mutation=='file_ref':result['file_ref']['file_uid']='wrong-file'
    if mutation=='media':result['artifact_ref']['media_type']='image/png'
    if mutation=='hash':result['content_hash']='sha256:'+'d'*64
    if mutation=='length':result['byte_length']=33
    if mutation=='plan_node':admitted['node_key']='wrong-node'
    if mutation=='expected_hash':admitted['expected_content_hash']='sha256:'+'d'*64;payload['expected_content_hash']=admitted['expected_content_hash']
    plan={'capability_id':'simulation.model_cache.file.fetch.request','steps':[{'operation_id':'teamcenter.model_file.fetch@1','payload':admitted}]}
    with store() as conn,conn.cursor() as cur:
        cur.execute('CREATE TABLE workmanship_sim_connector_runtime_plans(plan_id TEXT,actor_gid TEXT,tenant_gid TEXT,plan_json TEXT)')
        cur.execute('INSERT INTO workmanship_sim_connector_runtime_plans VALUES (%s,%s,%s,%s)',('file-op','1','2',json.dumps(plan)))
    cache=SimpleNamespace(repo=repo,_read=lambda *_:batch,output=lambda value:value)
    connector=SimpleNamespace(repository=SimpleNamespace(get_plan_result=lambda *_:{'status':'completed','outcome':{'steps':[{'result':result}]}}))
    with pytest.raises(CapabilityBusinessError,match='cache_file_(result_invalid|operation_mismatch)'):
        CacheFileProvider(cache,connector).result(payload,SimpleNamespace(user_gid='1',team_gid='2'))


def test_registered_file_specs_have_closed_normalized_schemas_and_transactional_admission():
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_files import specs
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for,governed_spec
    values=list(specs())
    assert len(values)==6
    for spec,handler in values:
        descriptor=descriptor_for(governed_spec(spec))
        assert descriptor.input_schema['additionalProperties'] is False
        assert descriptor.output_schema['additionalProperties'] is False
        assert 'project_scoped_exact_file' in descriptor.authorization_policy
        if '.batch.' in spec.id:
            assert {'docs/contracts/simulation.model_cache.file.fetch.batch.request@1.json','docs/contracts/simulation.model_cache.file.fetch.batch.result@1.json'} <= set(descriptor.transaction_policy['contract_refs'])
        if spec.id.endswith('.request'):assert handler.__capability_transactional__


@pytest.mark.parametrize('status',['queued','leased','executing','completed','failed','expired','outcome_unknown','manual_review_required'])
def test_file_status_schema_accepts_real_connector_states(status):
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_file_contracts import ADMISSION
    from backend.capabilities.validation_next import validate_payload
    validate_payload(ADMISSION['properties']['status'],status,label='status')
