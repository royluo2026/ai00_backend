import pytest
from pydantic import ValidationError
from plugins.agent.agent_backend.orchestration.models import GraphDraft


def payload():
    return {'axis': {'x_items':['准备','校核'],'y_items':['ME']}, 'nodes':[
        {'gid':'a','node_key':'a','title':'编制','x_item_key':'准备','y_item_key':'ME','home_scope_gid':'root','semantic_type':'action','implementation':{'kind':'agent','llm':True},'outputs':[{'key':'out','name':'方案','data_type':'document'}]},
        {'gid':'b','node_key':'b','title':'校核','x_item_key':'校核','y_item_key':'ME','home_scope_gid':'root','semantic_type':'measurement','inputs':[{'key':'in','name':'待校核','data_type':'document'}]}],
        'edges':[{'gid':'e','edge_type':'data','relation_semantics':'data','source_node_gid':'a','target_node_gid':'b','source_port_key':'out','target_port_key':'in'}],
        'workspace':{'scopes':[{'gid':'root','title':'ME'}],'tasks':[{'gid':'t','title':'工艺方案编制'}], 'views':[{'gid':'v','view_type':'task','task_gid':'t','axis':{'x_items':['准备','校核'],'y_items':['ME']},'placements':[{'node_gid':'a','x_item_key':'准备','y_item_key':'ME'},{'node_gid':'b','x_item_key':'校核','y_item_key':'ME'}]}]}}


def test_workspace_roundtrip_preserves_semantics_and_fixed_versions():
    graph=GraphDraft.model_validate(payload())
    assert graph.workspace.tasks[0].title=='工艺方案编制'
    assert graph.nodes[0].implementation.llm
    assert GraphDraft.model_validate(graph.model_dump()).nodes[1].semantic_type=='measurement'


def test_feedback_is_modelable_but_sequence_cycles_still_rejected():
    data=payload()
    data['edges'].append({'gid':'f','edge_type':'semantic','relation_semantics':'feedback','source_node_gid':'b','target_node_gid':'a'})
    assert GraphDraft.model_validate(data).edges[1].relation_semantics=='feedback'
    data['edges'][1]['relation_semantics']='sequence'
    data['edges'][0]['relation_semantics']='sequence'
    with pytest.raises(ValidationError,match='cycle'): GraphDraft.model_validate(data)


@pytest.mark.parametrize('case',['scope_cycle','missing_scope','duplicate_placement','port_type','bad_override'])
def test_invalid_workspace_rejected(case):
    data=payload()
    if case=='scope_cycle': data['workspace']['scopes'][0]['parent_gid']='root'
    if case=='missing_scope': data['nodes'][0]['home_scope_gid']='nope'
    if case=='duplicate_placement': data['workspace']['views'][0]['placements'].append(data['workspace']['views'][0]['placements'][0])
    if case=='port_type': data['nodes'][1]['inputs'][0]['data_type']='number'
    if case=='bad_override': data['workspace']['variants']=[{'gid':'var','task_gid':'t','stage_ref':'初版','node_overrides':{'a':{'gid':'spoof'}}}]
    with pytest.raises(ValidationError): GraphDraft.model_validate(data)


def test_legacy_graph_has_no_invented_workspace():
    assert GraphDraft(nodes=[],edges=[]).model_dump()['workspace'] is None


def test_parallel_implementation_status_and_local_slots_roundtrip():
    data=payload()
    data['nodes'][0]['implementation']={'kind':'human','status':'active','coordination':'human_review',
        'alternatives':[{'kind':'agent','status':'developing','llm':True,'label':'自动化替换'}]}
    data['workspace']['views'][0]['placements'][0].update(slot_x=-1,slot_y=2)
    graph=GraphDraft.model_validate(data)
    assert graph.nodes[0].implementation.alternatives[0].status=='developing'
    assert graph.workspace.views[0].placements[0].slot_x==-1
    from plugins.agent.agent_backend.orchestration.workspace_model import clone_revision_graph
    assert clone_revision_graph(graph).nodes[0].implementation.coordination=='human_review'


def test_parallel_implementation_missing_source_item_is_rejected():
    data=payload()
    data['nodes'][0]['implementation']['alternatives']=[{'kind':'program','source_item_gids':['missing']}]
    with pytest.raises(ValidationError,match='implementation item missing'):GraphDraft.model_validate(data)


@pytest.mark.parametrize('override', [
    {'b': {'inputs':[{'key':'in','name':'input','data_type':'number'}]}},
    {'a': {'implementation':{'kind':'agent','source_item_gids':['missing']}}},
])
def test_effective_variant_rejects_invalid_ports_and_implementation_refs(override):
    data=payload()
    data['workspace']['variants']=[{'gid':'variant','task_gid':'t','stage_ref':'prototype','node_overrides':override}]
    with pytest.raises(ValidationError): GraphDraft.model_validate(data)


def test_repository_extension_write_and_failure_are_atomic():
    from backend.tests.test_orchestration_repository import RecordingCursor,connection_factory,owned_version
    from plugins.agent.agent_backend.orchestration.repository import OrchestrationRepository
    cursor=RecordingCursor({'FROM workmanship_agent_orch_versions v':owned_version()},fail_on='INSERT INTO workmanship_agent_orch_workspaces')
    factory=connection_factory(cursor)
    with pytest.raises(RuntimeError,match='injected'):
        OrchestrationRepository(factory).save_graph('v',GraphDraft.model_validate(payload()),expected_revision=7,actor_gid='u',tenant_gid='tenant',project_gid='project')
    assert factory.connection.rolled_back and not factory.connection.committed


def test_repository_reads_extension_metadata():
    import json
    from backend.tests.test_orchestration_repository import RecordingCursor,connection_factory
    from plugins.agent.agent_backend.orchestration.repository import OrchestrationRepository
    data=payload()
    cursor=RecordingCursor({'SELECT v.mode,v.revision FROM workmanship_agent_orch_versions v':[{'mode':'fixed'}],
        'FROM workmanship_agent_orch_axis_views':[{'x_items_json':json.dumps(data['axis']['x_items']),'y_items_json':json.dumps(data['axis']['y_items'])}],
        'FROM workmanship_agent_orch_business_nodes':[dict(n,inputs_json=json.dumps(n.get('inputs',[])),outputs_json=json.dumps(n.get('outputs',[]))) for n in data['nodes']],
        'FROM workmanship_agent_orch_flow_edges':data['edges'],
        'FROM workmanship_agent_orch_workspaces':[{'definition_json':json.dumps({'workspace':data['workspace'],'nodes':{n['gid']:{k:n[k] for k in ('home_scope_gid','semantic_type','implementation') if k in n} for n in data['nodes']},'edges':{e['gid']:{k:e[k] for k in ('relation_semantics','source_port_key','target_port_key')} for e in data['edges']}})}]})
    graph=OrchestrationRepository(connection_factory(cursor)).get_graph('v',actor_gid='u',tenant_gid='tenant',project_gid='project')
    assert graph.nodes[0].implementation.llm
    assert graph.workspace.tasks[0].gid=='t'


def test_gateway_schema_accepts_closed_workspace_graph():
    import jsonschema
    from plugins.agent.agent_backend.capabilities.contracts import INPUT_SCHEMAS
    jsonschema.validate({'version_gid':'v','expected_revision':1,'graph':payload()},INPUT_SCHEMAS['agent.orchestration.organization.graph.save'])



def test_org_axes_inherit_parent_and_level_survives_version_clone():
    from plugins.agent.agent_backend.orchestration.workspace_model import normalize_org_axes,clone_revision_graph
    data=payload();data['nodes'][0]['level']=1
    data['workspace']['scopes'].append({'gid':'child','parent_gid':'root','title':'子组织'})
    data['workspace']['views'] += [{'gid':'root-view','view_type':'org','scope_gid':'root','axis':{'x_items':['准备','校核'],'y_items':['职责']},'placements':[]},{'gid':'child-view','view_type':'org','scope_gid':'child','axis':{'x_items':['旧轴'],'y_items':['职责']},'placements':[]}]
    graph=GraphDraft.model_validate(data);normalize_org_axes(graph)
    assert graph.workspace.views[-2].axis.y_items==['子组织']
    assert graph.workspace.views[-1].axis.x_items==['准备','校核']
    assert clone_revision_graph(graph).nodes[0].level==1
    data['nodes'][0]['level']=0
    with pytest.raises(ValidationError):GraphDraft.model_validate(data)
