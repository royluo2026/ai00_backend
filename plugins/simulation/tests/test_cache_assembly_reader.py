import json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from plugins.simulation.simulation_backend.data.cache_assembly_reader import read_assembly
from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CacheError
from plugins.simulation.simulation_backend.data.cloud_model_cache_snapshot import read, metadata

IDENTITY=dict(batch_id='a'*32,generation=None,snapshot_hash=None,schema_version=1)
MATRIX=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]

class Cursor:
    def __init__(self,case):self.case=case;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args):
        if 'SELECT manifest_json' in sql:self.rows=[dict(manifest_json=json.dumps(self.case.manifest))]
        elif 'AS fields_json' in sql:self.rows=[] if args[1] else deepcopy(self.case.rows)
        elif 'AS page_order' in sql:self.rows=[dict(node_key='root',page_order=0,structure_json=self.case.rows[0]['structure_json'])]
        else:raise AssertionError(sql)
    def fetchone(self):return self.rows.pop(0) if self.rows else None
    def fetchall(self):rows=self.rows;self.rows=[];return rows
    def fetchmany(self,n):rows=self.rows[:n];self.rows=self.rows[n:];return rows

class Connection:
    def __init__(self,case):self.case=case
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self,*args):return Cursor(self.case)

@pytest.fixture
def case():
    state=SimpleNamespace(calls=[],permissions=0)
    batch=dict(batch_id=IDENTITY['batch_id'],status='completed',node_count=1,source_selector={})
    state.manifest=metadata(batch,None)
    state.rows=[dict(node_key='root',structure_json=json.dumps(dict(parent_occurrence_id=None,name='Root',item_revision_uid='rev')),
        fields_json=json.dumps([None,dict(field='bl_plmxml_abs_xform',read_state='value',value_json=json.dumps(MATRIX)),dict(field='IMAN_Rendering',read_state='value',value_json='[]')]))]
    repo=SimpleNamespace(connect=lambda:Connection(state),_batch=lambda *args:batch)
    def pinned(*args,**kwargs):
        state.calls.append(kwargs)
        return read(repo,*args,**kwargs)
    repo.query_pinned=pinned
    def permission(*args):state.permissions+=1
    state.cache=SimpleNamespace(repo=repo,_read=permission)
    state.context=SimpleNamespace(team_gid='20')
    return state

def test_reader_uses_real_snapshot_read_manifest_and_initial_final_pins(case):
    result=read_assembly(case.cache,IDENTITY,case.context)
    assert result['identity']==IDENTITY and result['manifest']['node_count']==1
    assert result['nodes'][0]['absolute_transform']==MATRIX
    assert case.permissions==1 and len(case.calls)==2
    assert all(call==dict(scope='roots',projection='structure',page_size=1,expected_generation=None,expected_snapshot_hash=None) for call in case.calls)

@pytest.mark.parametrize('when',['initial','final'])
def test_identity_changes_are_rejected(case,when):
    original=case.cache.repo.query_pinned
    def changed(*args,**kwargs):
        result=original(*args,**kwargs)
        if len(case.calls)==(1 if when=='initial' else 2):result['identity']={**IDENTITY,'generation':'b'*32}
        return result
    case.cache.repo.query_pinned=changed
    with pytest.raises(CacheError,match='cache_snapshot_mismatch'):read_assembly(case.cache,IDENTITY,case.context)
    assert len(case.calls)==(1 if when=='initial' else 2)

@pytest.mark.parametrize('when',['initial','final'])
def test_node_count_changes_are_rejected(case,when):
    original=case.cache.repo.query_pinned
    def changed(*args,**kwargs):
        result=original(*args,**kwargs)
        if len(case.calls)==(1 if when=='initial' else 2):result['manifest']['node_count']=2
        return result
    case.cache.repo.query_pinned=changed
    with pytest.raises(CacheError,match='cache_snapshot_node_count_mismatch' if when=='initial' else 'cache_snapshot_mismatch'):
        read_assembly(case.cache,IDENTITY,case.context)

@pytest.mark.parametrize('field',['blXplmxml_abs_xform','IMANXRendering'])
def test_sql_like_wildcards_cannot_substitute_different_raw_field(case,field):
    fields=json.loads(case.rows[0]['fields_json']);fields[1 if field.startswith('bl') else 2]['field']=field
    case.rows[0]['fields_json']=json.dumps(fields)
    with pytest.raises(CacheError,match='cache_assembly_field_mismatch'):read_assembly(case.cache,IDENTITY,case.context)
