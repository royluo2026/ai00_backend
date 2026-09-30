import json
import sqlite3
import pytest
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.capability_v2.business_definition import business_definition_hash
from plugins.simulation.tests.test_viewer_open_completion import database, opened, signing, completion, counts
from plugins.simulation.tests.test_cache_open_evidence import make_cache, BINDING
from plugins.simulation.tests.test_viewer_interaction_provider import registry

KEY = ('simulation.environment.cache_source.live_document.bind', 1)

@pytest.fixture
def cache_completion(database, opened, completion):
    row = make_cache(opened)
    envelope = dict(cache_binding=BINDING, project_gid='50', insertion_instance_id='kept', source_selector={'kept':True})
    with sqlite3.connect(database) as db:
        db.execute('UPDATE workmanship_sim_connector_runtime_plans SET plan_json=?,outcome_json=?,plan_hash=?,outcome_hash=?',
            (json.dumps(row['plan_json']),json.dumps(row['outcome_json']),row['plan_hash'],row['outcome_hash']))
        db.execute("UPDATE workmanship_sim_vm_documents SET source_kind='teamcenter_cache_snapshot',content_sha256='',artifact_ref_json=?",
            (json.dumps(envelope),))
    descriptor = registry()[KEY][2]
    completion.context = completion.context.model_copy(update=dict(capability_version_gid=descriptor.capability_version_gid,
        business_definition_hash=business_definition_hash(descriptor)))
    return completion

def complete(case):
    return case.provider.bind_cache(case.payload, case.context).data

@pytest.mark.parametrize('role',['primary','inserted'])
def test_cache_completion_preserves_pins_and_commits_signed_grant_once(database, cache_completion, role):
    from backend.contracts.viewer_interaction_v1 import SignedGrant
    with sqlite3.connect(database) as db:
        db.execute('UPDATE workmanship_sim_vm_documents SET document_role=?',(role,))
    result = complete(cache_completion)
    assert SignedGrant.model_validate(result['grant']).verify_signature(cache_completion.public)
    assert complete(cache_completion) == result
    assert counts(database) == [1,1,1,1,1]
    with sqlite3.connect(database) as db:
        kind, encoded, content = db.execute('SELECT source_kind,artifact_ref_json,content_sha256 FROM workmanship_sim_vm_documents').fetchone()
        envelope = json.loads(encoded)
        assert kind == 'teamcenter_cache_snapshot'
        assert envelope['cache_binding'] == BINDING and envelope['insertion_instance_id'] == 'kept'
        assert envelope['package_hash'] == 'sha256:'+content
        assert db.execute('SELECT source_revision FROM workmanship_sim_viewer_source_associations').fetchone()[0] == content
        proof = json.loads(db.execute('SELECT proof_json FROM workmanship_sim_viewer_grant_evidence').fetchone()[0])
        assert proof['authorization_descriptor']['id'] == KEY[0]

@pytest.mark.parametrize('failure',['pin','owner','runtime','signer','proof'])
def test_cache_completion_rejects_mismatch_and_rolls_back(database, cache_completion, failure):
    with sqlite3.connect(database) as db:
        if failure == 'pin': db.execute("UPDATE workmanship_sim_vm_documents SET artifact_ref_json='{}'")
        elif failure == 'owner': db.execute("UPDATE workmanship_sim_vm_documents SET owner_gid='99'")
        elif failure == 'runtime': db.execute("UPDATE workmanship_sim_connector_runtime_devices SET runtime_generation=99")
        elif failure == 'proof': db.execute("CREATE TRIGGER fail_proof BEFORE INSERT ON workmanship_sim_viewer_grant_evidence BEGIN SELECT RAISE(ABORT,'proof failure'); END")
    if failure == 'signer': cache_completion.record['revoked'] = True
    with pytest.raises((CapabilityBusinessError,sqlite3.IntegrityError)): complete(cache_completion)
    assert counts(database) == [0,0,0,0,0]
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT content_sha256 FROM workmanship_sim_vm_documents').fetchone()[0] == ''
        assert db.execute('SELECT row_version FROM workmanship_sim_workspaces').fetchone()[0] == 1

@pytest.mark.parametrize('change',['artifact','pin','hash','dependency'])
def test_cache_authorization_rejects_mutated_package_after_binding(database, cache_completion, change):
    from types import SimpleNamespace
    from plugins.simulation.simulation_backend.data import workspace_repository
    from plugins.simulation.simulation_backend.data.viewer_interaction_repository import ViewerInteractionRepository
    from plugins.simulation.tests.test_teamcenter_launch_evidence import NOW
    result = complete(cache_completion)
    repository = ViewerInteractionRepository(connect=workspace_repository.get_simulation_conn)
    request = SimpleNamespace(workspace_gid='10',document_gid='11',source_association_id=result['binding']['source_association_id'])
    with repository.authorize_scope(cache_completion.context,request,NOW,allocate=False) as scope:
        assert scope['source_association_id'] == request.source_association_id
    with sqlite3.connect(database) as db:
        envelope = json.loads(db.execute('SELECT artifact_ref_json FROM workmanship_sim_vm_documents').fetchone()[0])
        if change == 'artifact': envelope['artifact_ref']['artifact_id'] = 'changed'
        elif change == 'pin': envelope['cache_binding']['batch_id'] = 'f'*32
        elif change == 'hash': envelope['package_hash'] = 'sha256:'+'0'*64
        else: envelope['package_dependencies'] = [{}]
        db.execute('UPDATE workmanship_sim_vm_documents SET artifact_ref_json=?',(json.dumps(envelope),))
    with pytest.raises(ValueError,match='interaction_binding_stale'):
        with repository.authorize_scope(cache_completion.context,request,NOW,allocate=False): pass
