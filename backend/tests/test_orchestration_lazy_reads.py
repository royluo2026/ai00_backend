import pytest
from jsonschema import validate
from backend.tests.test_orchestration_repository import RecordingCursor, connection_factory, owned_version
from backend.tests.test_orchestration_workspace_contract import payload
from plugins.agent.agent_backend.orchestration.repository import OrchestrationRepository, RevisionConflict, ResourceNotAccessible
from plugins.agent.agent_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
import json

PREFIX='agent.orchestration.organization.'
def repository():
    from plugins.agent.agent_backend.orchestration.models import GraphDraft
    graph=GraphDraft.model_validate(payload()).model_dump(mode='json')
    extension={'workspace':graph['workspace'],'nodes':{n['gid']:{k:n[k] for k in ('home_scope_gid','semantic_type','implementation')} for n in graph['nodes']},'edges':{}}
    cursor=RecordingCursor({'FROM workmanship_agent_orch_versions v':owned_version(),'FROM workmanship_agent_orch_workspaces':[{'definition_json':json.dumps(extension)}]})
    return OrchestrationRepository(connection_factory(cursor)),cursor,graph

def test_directory_reads_only_metadata_and_omits_unloaded_placements():
    repo,cursor,graph=repository()
    result=repo.get_organization_slice('v1',tenant_gid='tenant-1',actor_gid='u',projection='directory',expected_revision=7)
    assert result['complete'] is False and result['revision']==7
    assert result['graph']['nodes']==[] and all(not v['placements'] for v in result['graph']['workspace']['views'])
    assert not any('business_nodes' in sql or 'capability_bindings' in sql for sql,_ in cursor.executions)
    validate(result,OUTPUT_SCHEMAS[PREFIX+'graph.read'])

def test_lazy_read_checks_organization_and_revision_before_loading_children():
    repo,cursor,_=repository()
    with pytest.raises(RevisionConflict):repo.get_organization_slice('v1',tenant_gid='tenant-1',actor_gid='u',projection='directory',expected_revision=6)
    assert len(cursor.executions)==1
    with pytest.raises(ResourceNotAccessible):repo.get_organization_slice('v1',tenant_gid='user:u',actor_gid='u',projection='directory')

def test_unknown_view_and_node_are_refused():
    repo,cursor,_=repository()
    with pytest.raises(ValueError):repo.get_organization_slice('v1',tenant_gid='tenant-1',actor_gid='u',projection='view',view_gid='unknown')
    with pytest.raises(ResourceNotAccessible):repo.get_organization_slice('v1',tenant_gid='tenant-1',actor_gid='u',projection='node',node_gid='unknown')

def test_lazy_read_schema_preserves_old_full_read_and_rejects_scope_injection():
    schema=INPUT_SCHEMAS[PREFIX+'graph.read']
    validate({'version_gid':'v'},schema)
    validate({'version_gid':'v','projection':'view','view_gid':'local','expected_revision':7},schema)
