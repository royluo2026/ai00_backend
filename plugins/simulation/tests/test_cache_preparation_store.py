from copy import deepcopy
import pytest
from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.tests.test_cloud_model_cache import store,create,CloudModelCacheRepository
from plugins.simulation.tests.test_cache_preparation import projection
from plugins.simulation.simulation_backend.capabilities.cloud_model_cache import CloudModelCacheProvider
from plugins.simulation.simulation_backend.data.cache_assembly_preparation import prepare_batch,load_preparation,encode_preparation,decode_preparation

def test_prepared_metadata_is_shared_but_project_and_tenant_permissions_are_checked(store,monkeypatch):
    repo=CloudModelCacheRepository(store);batch=create(repo);source=projection();source['identity']['batch_id']=batch['batch_id']
    provider=CloudModelCacheProvider(repo,object()) # No Connector/FMS methods available.
    context=CapabilityContext(user_gid='1',team_gid='2',active_roles=('super_admin',))
    with store() as conn,conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_cloud_cache_batches SET status='completed',preparation_status='queued' WHERE batch_id=%s",(batch['batch_id'],))
    monkeypatch.setattr(repo,'query_pinned',lambda *a,**k:dict(identity=source['identity']))
    monkeypatch.setattr('plugins.simulation.simulation_backend.data.cache_assembly_preparation.read_assembly',lambda *a:deepcopy(source))
    prepare_batch(provider,batch['batch_id'],context)
    before=load_preparation(provider,source['identity'],context)
    monkeypatch.setattr('plugins.simulation.simulation_backend.capabilities.cloud_model_cache.can_manage_project',lambda actor,project:actor=='9' and project=='3')
    assert load_preparation(provider,source['identity'],CapabilityContext(user_gid='9',team_gid='2'))==before
    with pytest.raises(Exception,match='cache_project_forbidden'):
        load_preparation(provider,source['identity'],CapabilityContext(user_gid='8',team_gid='2'))
    with pytest.raises(Exception,match='cache_not_found'):
        load_preparation(provider,source['identity'],CapabilityContext(user_gid='9',team_gid='other'))

def test_large_metadata_roundtrip_preserves_hash_and_never_sends_a_large_insert(store,monkeypatch):
    # Reproduce a source larger than the DB packet limit; compression preserves exact JSON.
    value={'identity':{'snapshot_hash':'sha256:'+'a'*64},'assembly_xml':'<Transform>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</Transform>'*100000}
    assert len(str(value))>4*1024*1024
    encoded=encode_preparation(value)
    assert len(encoded)<256*1024 and decode_preparation(encoded)==value

def test_old_jt_upload_entry_points_fail_before_any_connector_or_database_access():
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_files import CacheFileProvider
    provider=CacheFileProvider(cache=object(),connector=object())
    for call in (provider.request,provider.request_batch):
        with pytest.raises(Exception) as failure:call({},None)
        assert failure.value.code=='cache_jt_upload_disabled'
