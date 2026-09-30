from copy import deepcopy
from xml.etree import ElementTree as ET
import pytest
from plugins.simulation.simulation_backend.application.cache_preparation import prepare_cached_assembly, scoped_preparation

BINDING=dict(batch_id='a'*32,generation='b'*32,snapshot_hash='sha256:'+'c'*64,schema_version=1)
M=[1,0,0,0,0,1,0,0,0,0,1,0,2,3,4,1]
REF=dict(dataset_uid='dataset',file_uid='file',file_name='bolt.jt',relation_type='IMAN_Rendering')
def projection():
    root=dict(node_key='root',parent_node_key=None,name='Root',item_revision_uid='r',absolute_transform=M,absolute_read_state='value',transform_state='root_absolute',geometry_refs=[],error_code=None)
    return dict(identity=BINDING,spatial_authority={'unit':'m'},nodes=[root,*[{**root,'node_key':key,'parent_node_key':'root','transform_state':'source_validated','geometry_refs':[REF],'absolute_transform':[*M[:12],x,3,4,1]} for key,x in [('a',10),('b',20)]]])

def test_preparation_has_tc_dependencies_without_artifacts_or_jt_bytes():
    value=prepare_cached_assembly(projection(),endpoint_id='tc-production')
    assert value['status']=='ready' and len(value['files'])==1
    assert value['files'][0]['file_uid']=='file'
    assert 'artifact_ref' not in str(value) and 'expected_content_hash' not in str(value)
    assert value['preparation_hash'].startswith('sha256:')
    assert '<PLMXML' in value['assembly_xml']
    assert len(value['node_dependencies']['root'])==1

def test_scopes_reuse_shared_preparation_but_keep_occurrence_positions():
    prepared=prepare_cached_assembly(projection(),endpoint_id='tc-production')
    a=scoped_preparation(prepared,'a',dict(workspace_gid='10',document_gid='11',name='W10'))
    b=scoped_preparation(prepared,'b',dict(workspace_gid='10',document_gid='11',name='W10'))
    assert a['dependencies']==b['dependencies']
    assert set(a['node_map'])=={'a'} and set(b['node_map'])=={'b'}
    assert '10 3 4 1' in a['assembly_xml'] and '20 3 4 1' in b['assembly_xml']
    assert 'W10' in a['assembly_xml']
    assert prepare_cached_assembly(projection(),endpoint_id='another-tc')['files'][0]['dependency_key']!=prepared['files'][0]['dependency_key']

def test_missing_coordinate_is_excluded_without_mutating_snapshot():
    source=projection();source['nodes'][1]['transform_state']='unavailable';before=deepcopy(source)
    prepared=prepare_cached_assembly(source,endpoint_id='tc')
    assert source==before and prepared['status']=='partial'
    assert prepared['excluded'][0]['node_key']=='a'
    scope=scoped_preparation(prepared,'a',dict(workspace_gid='10',document_gid='11',name='W10'))
    assert scope['dependencies']==[] and scope['excluded'][0]['node_key']=='a'

def test_unrecognized_scope_and_tampered_preparation_are_rejected():
    prepared=prepare_cached_assembly(projection(),endpoint_id='tc')
    with pytest.raises(ValueError,match='cache_scope_node_not_found'):scoped_preparation(prepared,'other',None)
    prepared['projection']['nodes'][1]['absolute_transform'][12]=999
    with pytest.raises(ValueError,match='cache_preparation_hash_mismatch'):scoped_preparation(prepared,'a',None)
