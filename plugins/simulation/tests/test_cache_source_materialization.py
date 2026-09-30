from plugins.simulation.simulation_backend.application.cache_source_materialization import select_cached_assembly, materialize_cache_nodes
import pytest

IDENTITY = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
FILE = dict(dataset_uid='dataset',file_uid='file',file_name='part.jt',relation_type='IMAN_Rendering')
def node(key, parent=None, error=None, geometry=None):
    return dict(node_key=key,parent_node_key=parent,name=key,item_revision_uid='revision',
        absolute_transform=list(IDENTITY),absolute_read_state='value',root_transform=IDENTITY if parent is None else None,relative_transform=IDENTITY if parent else None,
        transform_state='missing' if error else 'source_validated' if parent else 'root_absolute',
        error_code=error,geometry_refs=[] if geometry is None else geometry)
def choose(nodes):
    return select_cached_assembly(dict(nodes=nodes,spatial_authority={'installation_verified':False,'evidence':'documented'}))


def test_scoped_subtree_keeps_world_position_without_parent_or_sibling_geometry():
    nodes=[node('r',geometry=[{**FILE,'file_uid':'parent'}]),node('a','r',geometry=[FILE]),
           node('child','a',geometry=[FILE]),node('sibling','r',geometry=[{**FILE,'file_uid':'other'}])]
    nodes[1]['absolute_transform'][12]=12
    projection=dict(nodes=nodes,spatial_authority={})
    selected=select_cached_assembly(projection,root_node_key='a')
    assert [n['node_key'] for n in selected['nodes']]==['a','child']
    assert selected['nodes'][0]['parent_node_key'] is None
    assert [f['file_uid'] for f in selected['files']]==['file']
    assert not selected['excluded']
    rows=materialize_cache_nodes(selected,{('dataset','file'):{'artifact_id':'exact'}})
    assert rows[1]['relative_transform'][12]==12
    assert nodes[1]['parent_node_key']=='r'
    with pytest.raises(ValueError,match='cache_scope_node_not_found'):
        select_cached_assembly(projection,root_node_key='unknown')


def test_scoped_selection_preserves_missing_placement_reason():
    projection=dict(nodes=[node('r'),node('a','r','relative_missing_absolute_may_be_placeholder',geometry=[FILE]),
                           node('b','a',geometry=[FILE])],spatial_authority={})
    selected=select_cached_assembly(projection,root_node_key='a')
    assert selected['excluded'][0]['node_key']=='a'
    assert selected['files'][0]['node_key']=='b'

def test_missing_geometry_is_excluded_without_blocking_valid_world_placed_descendants():
    result=choose([node('r'),node('a','r',geometry=[FILE]),node('b','r','relative_missing_absolute_may_be_placeholder',geometry=[FILE]),node('c','b',geometry=[FILE])])
    assert [n['node_key'] for n in result['nodes']]==['r','a','b','c']
    assert result['excluded']==[{'node_key':'b','name':'b','error_code':'relative_missing_absolute_may_be_placeholder'}]
    assert result['nodes'][2]['geometry_refs']==[]
    assert result['spatial_authority']['installation_verified'] is False

def test_logical_groups_need_no_source_transform_and_geometry_uses_absolute_once():
    group=node('r',error='relative_missing_absolute_may_be_placeholder')
    part=node('a','r',geometry=[FILE]);part['absolute_transform'][12]=12
    part['relative_transform']=[*IDENTITY];part['relative_transform'][12]=3
    selected=choose([group,part]);assert not selected['excluded']
    rows=materialize_cache_nodes(selected,{('dataset','file'):{'artifact_id':'exact'}})
    assert rows[0]['relative_transform']==IDENTITY and rows[1]['relative_transform']==IDENTITY
    assert rows[2]['parent_node_key']=='a' and rows[2]['relative_transform'][12]==12
    assert rows[2]['artifact_refs']==[{'artifact_id':'exact'}]
    assert part['relative_transform'][12]==3


def test_repeated_parts_keep_occurrences_and_deduplicate_exact_file_requests():
    source=[node('r'),node('a','r',geometry=[FILE]),node('b','r',geometry=[FILE])]
    result=choose(source)
    assert len(result['nodes'])==3 and len(result['files'])==1
    assert source[0]['relative_transform'] is None
    assert result['nodes'][0]['placement_mode']=='synthetic_world_group'

def test_unknown_geometry_does_not_turn_into_verified_empty_assembly():
    source=node('r');source['geometry_refs']=None
    result=choose([source])
    assert result['nodes'][0]['geometry_refs']==[] and not result['files']
    assert result['excluded'][0]['error_code']=='cache_geometry_references_unavailable'

@pytest.mark.parametrize('nodes,error', [([node('a','missing')],'cache_node_orphan'),([node('a','b'),node('b','a')],'cache_node_cycle'),([node('a'),node('a')],'cache_node_duplicate')])
def test_invalid_graph_is_not_silently_truncated(nodes,error):
    with pytest.raises(ValueError,match=error):choose(nodes)
