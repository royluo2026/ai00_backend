from unittest.mock import Mock
import pytest
from plugins.agent.agent_backend.orchestration.reference_resolver import ReferenceResolver
from plugins.agent.agent_backend.orchestration.service import OrchestrationService,PublishBlocked
from backend.tests.test_orchestration_service import publishable_graph


def test_fixed_context_version_does_not_resolve_as_latest():
    resolver=ReferenceResolver(lookups={'knowledge':lambda gid,actor:{'resolved':True,'version':'v3'}})
    result=resolver.resolve_many([{'ref_type':'knowledge','ref_gid':'doc','ref_version':'v2'}],'u')
    assert result[0]['resolved'] is False
    assert result[0]['bound_version']=='v2'
    assert result[0]['version']=='v3'


def test_publish_passes_fixed_version_to_owner_resolver():
    graph=publishable_graph(0)
    graph.items=[]
    from plugins.agent.agent_backend.orchestration.models import DecompositionItem,ContextBinding
    graph.items.append(DecompositionItem(gid='i',title='manual',item_type='human_task'))
    graph.context_bindings.append(ContextBinding(gid='c',source_item_gid='i',ref_type='knowledge',ref_gid='doc',ref_version='v2',purpose='guidance'))
    repo,resolver=Mock(),Mock();repo.get_graph.return_value=graph;resolver.resolve_many.return_value=[{'resolved':True}]
    OrchestrationService(repo,resolver).publish('v',expected_revision=1,actor_gid='u',tenant_gid='t',project_gid='p')
    assert resolver.resolve_many.call_args.args[0][0]['ref_version']=='v2'


def test_revision_remaps_stored_ids_but_preserves_node_keys_and_relationships():
    from plugins.agent.agent_backend.orchestration.workspace_model import clone_revision_graph
    from backend.tests.test_orchestration_workspace_contract import payload
    from plugins.agent.agent_backend.orchestration.models import GraphDraft
    old=GraphDraft.model_validate(payload());new=clone_revision_graph(old)
    assert new.nodes[0].gid!=old.nodes[0].gid
    assert new.nodes[0].node_key==old.nodes[0].node_key
    assert new.edges[0].source_node_gid==new.nodes[0].gid
    assert new.workspace.views[0].placements[0].node_gid==new.nodes[0].gid


def test_runtime_rejects_unimplemented_feedback_before_starting_run():
    import json
    from backend.tests.test_orchestration_repository import RecordingCursor,connection_factory
    from plugins.agent.agent_backend.orchestration.repository import OrchestrationRepository,InvalidTransition
    cursor=RecordingCursor({'SELECT v.gid FROM workmanship_agent_orch_versions v':[{'gid':'v'}],
        'FROM workmanship_agent_orch_workspaces':[{'definition_json':json.dumps({'edges':{'e':{'relation_semantics':'feedback'}}})}]})
    with pytest.raises(InvalidTransition,match='closed_loop'):
        OrchestrationRepository(connection_factory(cursor)).create_run_with_started_event(panorama_gid='p',version_gid='v',frozen_context={},actor_gid='u',tenant_gid='t',project_gid='p')
    assert not any('INSERT INTO workmanship_agent_orch_runs' in sql for sql,_ in cursor.executions)


def test_unverified_skill_cannot_publish_as_governed_implementation():
    graph=publishable_graph(0)
    graph.nodes[0].implementation.kind='agent'
    graph.nodes[0].implementation.skill_gid='skill'
    graph.nodes[0].implementation.skill_version='v2'
    repo,resolver=Mock(),Mock();repo.get_graph.return_value=graph
    resolver.resolve_many.return_value=[{'resolved':False,'ref_gid':'skill'}]
    with pytest.raises(PublishBlocked,match='skill'):
        OrchestrationService(repo,resolver).publish('v',expected_revision=1,actor_gid='u',tenant_gid='t',project_gid='p')
    repo.publish_version.assert_not_called()


def test_parallel_skill_is_verified_and_revision_remaps_each_option_sources():
    from plugins.agent.agent_backend.orchestration.workspace_model import Implementation,clone_revision_graph
    graph=publishable_graph(1)
    item_gid=graph.items[0].gid
    graph.nodes[0].implementation=Implementation(kind='human',status='active',coordination='transition',
        alternatives=[{'kind':'agent','status':'developing','skill_gid':'replacement-skill','skill_version':'v2','source_item_gids':[item_gid]}])
    new=clone_revision_graph(graph)
    assert new.nodes[0].implementation.alternatives[0].source_item_gids==[new.items[0].gid]
    repo,resolver=Mock(),Mock();repo.get_graph.return_value=graph
    resolver.resolve_many.return_value=[{'resolved':False,'ref_gid':'replacement-skill'}]
    with pytest.raises(PublishBlocked,match='replacement-skill'):
        OrchestrationService(repo,resolver).publish('v',expected_revision=1,actor_gid='u',tenant_gid='t',project_gid='p')
    assert {'ref_type':'skill','ref_gid':'replacement-skill','ref_version':'v2'} in resolver.resolve_many.call_args.args[0]
