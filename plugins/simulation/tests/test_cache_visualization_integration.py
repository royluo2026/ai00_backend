"""The online cache selector is compatible code, not a frozen-viewer replacement."""
import json
from types import SimpleNamespace

import pytest
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.simulation.tests.test_cloud_model_cache import store, create, SELECTOR
from plugins.simulation.tests.test_viewer_interaction_provider import registry
from plugins.simulation.tests.test_teamcenter_opened_source_evidence import opened_evidence, seal, verify
from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CloudModelCacheRepository, CacheError
from plugins.simulation.simulation_backend.capabilities import connector_runtime as runtime


@pytest.mark.parametrize('structure', [None, [], 'invalid', 42])
def test_corrupt_cache_node_has_stable_error(store, structure):
    repo=CloudModelCacheRepository(store);batch=create(repo)
    with store() as conn,conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s WHERE batch_id=%s',('completed',batch['batch_id']))
        cur.execute('INSERT INTO workmanship_sim_cloud_cache_nodes(batch_id,node_key,data_json) VALUES(%s,%s,%s)',
                    (batch['batch_id'],'node',json.dumps({'structure':structure})))
    with pytest.raises(CacheError,match='cache_source_identity_missing'):
        repo.resolve_visualization_node(batch['batch_id'],'2','node')


def test_project_denial_precedes_cache_state_and_node_lookup(store, monkeypatch):
    repo=CloudModelCacheRepository(store);batch=create(repo)  # Not completed; also no requested node.
    monkeypatch.setattr('plugins.simulation.simulation_backend.data.cloud_model_cache_repository.CloudModelCacheRepository',lambda:repo)
    monkeypatch.setattr('plugins.simulation.simulation_backend.capabilities.cloud_model_cache.admin',lambda _:False)
    monkeypatch.setattr('backend.platform_sdk.project_access.can_manage_project',lambda *_:False)
    with pytest.raises(CapabilityBusinessError) as error:
        runtime._resolve_cache_visualization_source({'batch_id':batch['batch_id'],'node_key':'missing'},
            CapabilityContext(user_gid='1',team_gid='2',source='web'))
    assert error.value.code=='cache_source_forbidden'


def test_authorized_cache_resolves_only_selected_revision(store, monkeypatch):
    repo=CloudModelCacheRepository(store);batch=create(repo)
    selector=dict(endpoint_id='tc-production',object_uid='root',item_revision_uid='root',bom_view_uid='view',
        revision_rule='Latest Working',configuration_date='2026-09-29T00:00:00Z')
    with store() as conn,conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET selector_json=%s WHERE batch_id=%s',(json.dumps(selector),batch['batch_id']))
        cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s WHERE batch_id=%s',('completed',batch['batch_id']))
        cur.execute('INSERT INTO workmanship_sim_cloud_cache_nodes(batch_id,node_key,data_json) VALUES(%s,%s,%s)',
            (batch['batch_id'],'occ',json.dumps({'structure':{'occurrence_id':'occ','item_revision_uid':'selected-revision'}})))
    monkeypatch.setattr('plugins.simulation.simulation_backend.data.cloud_model_cache_repository.CloudModelCacheRepository',lambda:repo)
    monkeypatch.setattr('plugins.simulation.simulation_backend.capabilities.cloud_model_cache.admin',lambda _:False)
    monkeypatch.setattr('backend.platform_sdk.project_access.can_manage_project',lambda actor,project:(actor,project)==('1','3'))
    result=runtime._resolve_cache_visualization_source({'batch_id':batch['batch_id'],'node_key':'occ'},
        CapabilityContext(user_gid='1',team_gid='2',source='web'))
    assert result=={**selector,'object_uid':'selected-revision','item_revision_uid':'selected-revision','bom_view_uid':''}


@pytest.mark.parametrize('version', [2, 3])
def test_opened_source_receipt_accepts_supported_request_versions(version):
    row,device=opened_evidence();row['plan_json']['major_version']=version;seal(row)
    assert verify(row,device)['document_session']==row['outcome_json']['steps'][0]['result']['document_identity']['document_session']


def test_unknown_request_version_is_not_admitted_as_compatible_evidence():
    row,device=opened_evidence();row['plan_json']['major_version']=4;seal(row)
    with pytest.raises(ValueError):verify(row,device)


def test_new_capability_versions_keep_existing_desktop_consumer_version():
    for key in [('simulation.teamcenter.visualization.launch.request',3),('simulation.teamcenter.visualization.insert.request',2)]:
        descriptor=registry()[key][2]
        assert all(item['version_constraint']=='==1' for item in descriptor.consumer_refs)
