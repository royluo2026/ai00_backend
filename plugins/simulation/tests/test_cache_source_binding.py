import json
from types import SimpleNamespace
import pytest
from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.simulation_backend.capabilities.environment_documents import EnvironmentDocumentProvider, specs
from plugins.simulation.simulation_backend.data.workspace_repository import WorkspaceRepository
from plugins.simulation.tests.test_environment_document_repository import _install

IDENTITY = {'batch_id': 'a'*32, 'generation': 'b'*32, 'snapshot_hash': None, 'schema_version': 1}

def test_cache_binding_validates_server_snapshot_before_persisting():
    calls=[]
    class Cache:
        def query_pinned(self, payload, context):
            calls.append(('read',payload,context))
            return SimpleNamespace(data={'identity':IDENTITY,'manifest':{'status':'completed','project_gid':'55','source_selector':{},'node_count':20},'nodes':[],'next_cursor':None})
    class Repo:
        def bind_cache_source(self, **kwargs):
            calls.append(('bind',kwargs));return {'document_gid':'9'}
    provider=EnvironmentDocumentProvider(Repo(),cache_provider=Cache())
    ctx=CapabilityContext(user_gid='30',team_gid='20',request_id='test')
    result=provider.bind_cache({'workspace_gid':'10','expected_row_version':3,'display_name':'Old','insertion_instance_id':'insert-1','cache_binding':IDENTITY},ctx)
    assert result.data['document_gid']=='9'
    assert calls[0][0]=='read' and calls[1][0]=='bind'
    assert calls[0][1]['expected_generation']==IDENTITY['generation']
    assert calls[1][1]['binding']==IDENTITY

def test_denied_cache_read_never_creates_document():
    class Cache:
        def query_pinned(self,*_): raise ValueError('cache_project_forbidden')
    class Repo:
        def bind_cache_source(self,**_): pytest.fail('must not bind')
    provider=EnvironmentDocumentProvider(Repo(),cache_provider=Cache())
    with pytest.raises(ValueError,match='cache_project_forbidden'):
        provider.bind_cache({'workspace_gid':'10','cache_binding':IDENTITY},CapabilityContext(user_gid='30',team_gid='20',request_id='test'))

def test_cache_source_is_persisted_as_binding_not_fake_artifact(monkeypatch):
    cursor=_install(monkeypatch,[{'row_version':3},None,None,{'position':1}])
    result=WorkspaceRepository().bind_cache_source(workspace_gid='10',expected_workspace_version=3,
        binding=IDENTITY,manifest={'project_gid':'55','source_selector':{}},display_name='old batch',
        insertion_instance_id='insert-1',tenant_gid='20',actor_gid='30')
    assert result['document_gid']=='9001'
    sql,values=next(call for call in cursor.calls if call[0].startswith('INSERT INTO workmanship_sim_vm_documents'))
    envelope=next(json.loads(value) for value in values if isinstance(value,str) and value.startswith('{'))
    assert envelope['cache_binding']==IDENTITY
    assert 'artifact_id' not in envelope
    assert 'teamcenter_cache_snapshot' in values

def test_search_v2_exposes_binding_while_v1_retains_closed_shape(monkeypatch):
    from backend.capabilities.validation_next import validate_payload
    row={'document_gid':40,'workspace_gid':10,'role':'primary','display_name':'old',
         'media_type':'application/vnd.siemens.teamcenter.visualization-document',
         'artifact_ref_json':json.dumps({'cache_binding':IDENTITY,'source_selector':{}}),
         'source_kind':'teamcenter_cache_snapshot','source_identity_hash':'a'*64,'content_sha256':'',
         'portability':'portable','connector_device_id':None,'sort_order':0,'row_version':1}
    for version in (1,2):
        _install(monkeypatch,[[dict(row)],[]])
        provider=EnvironmentDocumentProvider(WorkspaceRepository())
        spec,handler=next((s,h) for s,h in specs(provider) if s.id=='simulation.environment.model_document.search' and s.version==version)
        result=handler({'workspace_gid':'10'},CapabilityContext(user_gid='30',team_gid='20',request_id='test')).data
        validate_payload(spec.output_schema,result,label='output')
        assert result['items'][0]['artifact_ref'] is None
        assert result['items'][0].get('cache_binding')==(IDENTITY if version==2 else None)

def test_cache_binding_descriptor_declares_workspace_revision_and_query_dependency():
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
    spec=next(s for s,_ in specs() if s.id=='simulation.environment.cache_source.bind')
    descriptor=descriptor_for(spec)
    assert descriptor.concurrency_policy=='expected_version'
    assert descriptor.expected_version_payload_path=='expected_row_version'
    assert 'simulation.model_cache.query@2' in descriptor.transaction_policy['dependencies']

def test_stale_workspace_cannot_create_cached_document(monkeypatch):
    cursor=_install(monkeypatch,[{'row_version':4}])
    with pytest.raises(Exception,match='version_conflict'):
        WorkspaceRepository().bind_cache_source(workspace_gid='10',expected_workspace_version=3,
            binding=IDENTITY,manifest={'project_gid':'55'},display_name='old',
            insertion_instance_id='insert-1',tenant_gid='20',actor_gid='30')
    assert not any(sql.startswith('INSERT') for sql,_ in cursor.calls)

def test_two_cache_batches_keep_distinct_source_identities(monkeypatch):
    saved=[]
    for batch_id in ('a'*32,'c'*32):
        cursor=_install(monkeypatch,[{'row_version':3},None,{'gid':22},{'position':1}])
        WorkspaceRepository().bind_cache_source(workspace_gid='10',expected_workspace_version=3,
            binding={**IDENTITY,'batch_id':batch_id},manifest={'project_gid':'55'},display_name='old',
            insertion_instance_id='insert-1',tenant_gid='20',actor_gid='30')
        _,values=next(call for call in cursor.calls if call[0].startswith('INSERT INTO workmanship_sim_vm_documents'))
        saved.append(values)
    assert saved[0][-1]!=saved[1][-1]
    assert saved[0][4]=='inserted' and saved[1][4]=='inserted'
