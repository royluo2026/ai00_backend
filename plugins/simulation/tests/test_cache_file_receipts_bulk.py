import json,hashlib,base64
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives import hashes
from backend.contracts.connector_execution_plan_v2 import canonicalize_v2,compute_plan_hash,outcome_signature_bytes,P256_ORDER
from plugins.simulation.simulation_backend.data.cache_file_receipts_bulk import find_completed_bulk,verify_receipt_row
from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CacheError
IDENTITY={'batch_id':'a'*32,'generation':'b'*32,'snapshot_hash':None,'schema_version':1}
REF={'dataset_uid':'dataset','file_uid':'file','file_name':'part.jt','relation_type':'IMAN_Rendering'}
CTX=SimpleNamespace(user_gid='user-001',team_gid='tenant-001')
MEMBER={'node_key':'node','item_revision_uid':'rev','file_ref':REF}
def record(hash_char="c"):
 vector=json.loads((Path(__file__).parents[3]/'backend/tests/fixtures/connector_execution_plan_v2.json').read_text())
 plan=vector['plan'];plan['capability_id']='simulation.model_cache.file.fetch.request'
 payload={**IDENTITY,'node_key':'node','item_revision_uid':'rev','file_ref':REF,'expected_content_hash':None}
 plan['steps'][0]['operation_id']='teamcenter.model_file.fetch@1';plan['steps'][0]['payload']=payload;plan['steps'][0]['payload_hash']='sha256:'+hashlib.sha256(canonicalize_v2(payload)).hexdigest();plan['plan_hash']=compute_plan_hash(plan)
 file={**{k:payload[k] for k in ['node_key','item_revision_uid','file_ref']},'identity':IDENTITY,'artifact_ref':{'artifact_id':'artifact','media_type':'model/jt','sha256':hash_char*64,'byte_size':32,'version':1},'content_hash':'sha256:'+hash_char*64,'byte_length':32,'acquired_at':'2026-09-28T00:00:00Z','captured_bytes_verified':False}
 out=vector['outcome'];out['plan_hash']=plan['plan_hash'];out['steps'][0]['result']=file;out['steps'][0]['result_hash']='sha256:'+hashlib.sha256(canonicalize_v2(file)).hexdigest()
 key=ec.generate_private_key(ec.SECP256R1());pub=key.public_key().public_numbers();b64=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
 jwk={'kty':'EC','crv':'P-256','x':b64(pub.x.to_bytes(32,'big')),'y':b64(pub.y.to_bytes(32,'big'))}
 r,s=decode_dss_signature(key.sign(outcome_signature_bytes(out),ec.ECDSA(hashes.SHA256())));s=min(s,P256_ORDER-s);out['signature']=b64(r.to_bytes(32,'big')+s.to_bytes(32,'big'))
 return {'plan_id':plan['plan_id'],'plan_json':json.dumps(plan),'outcome_json':json.dumps(out),'plan_hash':plan['plan_hash'],'outcome_hash':hashlib.sha256(canonicalize_v2(out)).hexdigest(),'device_signing_jwk':json.dumps(jwk),'stored_device_key_id':out['device_key_id'],'cache_file_node':'node','cache_file_revision':'rev','cache_file_dataset':'dataset','cache_file_uid':'file','cache_file_content_hash':file['content_hash']}

def batch_record():
 from plugins.simulation.simulation_backend.capabilities.connector_runtime import build_file_batch_steps
 vector=json.loads((Path(__file__).parents[3]/'backend/tests/fixtures/connector_execution_plan_v2.json').read_text())
 plan=vector['plan'];plan['capability_id']='simulation.model_cache.file.fetch.batch.request';plan['plan_id']='batch-plan-002'
 identity={**IDENTITY,'snapshot_hash':'sha256:'+'e'*64}
 members=[
  {**identity,'node_key':'node','item_revision_uid':'rev','file_ref':REF,'expected_content_hash':None},
  {**identity,'node_key':'node-2','item_revision_uid':'rev-2','file_ref':{**REF,'file_uid':'file-2'},'expected_content_hash':None},
 ]
 plan['steps']=build_file_batch_steps(identity,{'endpoint_id':'tc-production','object_uid':'root'},members)
 plan['plan_hash']=compute_plan_hash(plan)
 preflight={'identity':identity,'files':[{'step_id':f'step-{i+2:05d}','node_key':m['node_key'],'item_revision_uid':m['item_revision_uid'],'file_ref':m['file_ref'],'file_size':32} for i,m in enumerate(members)],'total_byte_length':64,'error_code':None}
 fetched={'identity':identity,'node_key':'node','item_revision_uid':'rev','file_ref':REF,'artifact_ref':{'artifact_id':'artifact-1','media_type':'model/jt','sha256':'c'*64,'byte_size':32,'version':1},'content_hash':'sha256:'+'c'*64,'byte_length':32,'acquired_at':'2026-09-28T00:00:00Z','captured_bytes_verified':False}
 out=vector['outcome'];out['plan_id']=plan['plan_id'];out['plan_hash']=plan['plan_hash'];out['overall_status']='failed_without_effect'
 source=out['steps'][0]
 def step(step_id,status,result,error=None):
  value={**source,'step_id':step_id,'status':status,'result':result,'error_code':error,'result_hash':None,'reconciliation_state':'not_required'}
  if status=='succeeded':value['result_hash']='sha256:'+hashlib.sha256(canonicalize_v2(result)).hexdigest()
  return value
 out['steps']=[step('step-00001','succeeded',preflight),step('step-00002','succeeded',fetched),step('step-00003','failed_without_effect',None,'file_not_found')]
 private=ec.derive_private_key(2,ec.SECP256R1());pub=private.public_key().public_numbers();b64=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
 jwk={'kty':'EC','crv':'P-256','x':b64(pub.x.to_bytes(32,'big')),'y':b64(pub.y.to_bytes(32,'big'))}
 r,s=decode_dss_signature(private.sign(outcome_signature_bytes(out),ec.ECDSA(hashes.SHA256())));s=min(s,P256_ORDER-s);out['signature']=b64(r.to_bytes(32,'big')+s.to_bytes(32,'big'))
 return {'plan_id':plan['plan_id'],'plan_json':json.dumps(plan),'outcome_json':json.dumps(out),'plan_hash':plan['plan_hash'],'outcome_hash':hashlib.sha256(canonicalize_v2(out)).hexdigest(),'device_signing_jwk':json.dumps(jwk),'stored_device_key_id':out['device_key_id']},identity
def test_receipt_rechecks_signature_plan_identity_and_full_file():
 row=record();out=verify_receipt_row(row,IDENTITY,MEMBER,CTX)
 assert out['status']=='completed' and out['file']['byte_length']==32
@pytest.mark.parametrize('mutation',['signature','outcome_hash','identity','index_hash','device_key'])
def test_receipt_rejects_unverified_or_wrong_identity(mutation):
 row=record()
 if mutation=='signature':
  value=json.loads(row['outcome_json']);value['signature']='A'*86;row['outcome_json']=json.dumps(value)
 elif mutation=='outcome_hash':row['outcome_hash']='0'*64
 elif mutation=='identity':row['plan_id']='wrong'
 elif mutation=='index_hash':row['cache_file_content_hash']='sha256:'+'d'*64
 else:row['stored_device_key_id']='wrong-key'
 with pytest.raises(CacheError):verify_receipt_row(row,IDENTITY,MEMBER,CTX)

def test_batch_receipt_reuses_only_signed_successful_members_from_partial_plan():
 from plugins.simulation.simulation_backend.data.cache_file_receipts_bulk import verify_batch_receipt_row
 row,binding=batch_record();result=verify_batch_receipt_row(row,binding,CTX)
 assert [item['status'] for item in result['files']]==['succeeded','failed_without_effect']
 assert result['files'][0]['file']['artifact_ref']['sha256']=='c'*64
 row,binding=batch_record();tampered=json.loads(row['plan_json']);tampered['steps'][1]['payload']['file_ref']['file_uid']='foreign';row['plan_json']=json.dumps(tampered)
 with pytest.raises(CacheError):verify_batch_receipt_row(row,binding,CTX)
class Cursor:
 def __init__(self,provider):self.p=provider;self.rows=[]
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def execute(self,sql,params):
  self.p.calls.append((sql,params))
  if sql.startswith('SHOW COLUMNS'):
   names=['cache_file_batch_plan','cache_file_batch_generation','cache_file_batch_snapshot_hash'] if self.p.has_batch_index else []
   self.rows=[{'Field':name} for name in names]
  elif 'cloud_cache_nodes' in sql:
   self.rows=[{'node_key':key,'revision_json':json.dumps(m['item_revision_uid']),'geometry_json':json.dumps({'field':'IMAN_Rendering','read_state':'value','value_json':json.dumps([m['file_ref']])})} for key in params[2:] if (m:=self.p.member_map.get(key))]
  elif 'cache_file_batch_plan' in sql or "JSON_EXTRACT(p.plan_json,'$.capability_id')" in sql:
   self.rows=self.p.batch_records.copy()
  else:self.rows=self.p.records.copy()
 def fetchall(self):return self.rows
 def fetchmany(self,n):a=self.rows[:n];self.rows=self.rows[n:];return a
class Conn:
 def __init__(self,p):self.p=p
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def cursor(self,*a,**kw):return Cursor(self.p)
def provider(records,members=None):
 p=SimpleNamespace(calls=[],records=records,batch_records=[],has_batch_index=False,member_map={m["node_key"]:m for m in (members or [MEMBER])})
 repo=SimpleNamespace(connect=lambda:Conn(p),query_pinned=lambda *a,**kw:{'identity':IDENTITY})
 p.cache=SimpleNamespace(repo=repo,_read=lambda *a:None);return p
def test_bulk_uses_chunk_queries_not_per_member_source_or_count():
 p=provider([record()]);out=find_completed_bulk(IDENTITY,[MEMBER]*400,CTX,provider=p)
 assert len(out['results'])==400 and out['missing_count']==0
 assert len(p.calls)==4
 assert all('actor_gid=%s' in sql and 'tenant_gid=%s' in sql for sql,params in p.calls if 'SELECT' in sql and 'runtime_plans' in sql)
 assert not any('COUNT(' in sql for sql,params in p.calls)

def test_unknown_batch_without_outcome_is_not_a_receipt_and_does_not_poison_lookup():
 row,binding=batch_record()
 plan=json.loads(row['plan_json']);member={key:plan['steps'][1]['payload'][key] for key in ('node_key','item_revision_uid','file_ref')}
 p=provider([],members=[member]);p.cache.repo.query_pinned=lambda *a,**kw:{'identity':binding}
 p.batch_records=[{**row,'outcome_json':None},row]
 result=find_completed_bulk(binding,[member],CTX,provider=p)
 assert result['missing_count']==0
 assert result['results'][0]['file']['artifact_ref']['sha256']=='c'*64
 p.batch_records=[{**row,'outcome_json':None}]
 assert find_completed_bulk(binding,[member],CTX,provider=p)['results']==[None]
def test_bulk_no_receipt_and_membership_failure():
 assert find_completed_bulk(IDENTITY,[MEMBER],CTX,provider=provider([]))['missing_count']==1
 with pytest.raises(CacheError,match='cache_file_not_referenced'):find_completed_bulk(IDENTITY,[{**MEMBER,'file_ref':{**REF,'file_uid':'foreign'}}],CTX,provider=provider([]))
def test_bulk_conflict_never_picks_latest():
 row=record();other=record('d');other['plan_id']='plan-002'
 with pytest.raises(CacheError):find_completed_bulk(IDENTITY,[MEMBER],CTX,provider=provider([row,other]))

def test_unique_member_queries_scale_with_chunks_and_missing_order():
 members=[{**MEMBER,'node_key':'node-'+str(i),'file_ref':{**REF,'file_uid':'file-'+str(i)}} for i in range(400)]
 p=provider([],members);out=find_completed_bulk(IDENTITY,members,CTX,provider=p,chunk_size=200)
 assert out['results']==[None]*400 and out['missing_count']==400
 assert len(p.calls)==6
 assert sum('cloud_cache_nodes' in sql for sql,params in p.calls)==2
 assert sum('runtime_plans' in sql and 'SELECT' in sql for sql,params in p.calls)==3

def test_pinned_hash_ignores_unselected_old_key_but_unpinned_fails_closed():
 selected=record();other=record('d');other['stored_device_key_id']='retired-key'
 request={**MEMBER,'expected_content_hash':'sha256:'+'c'*64}
 out=find_completed_bulk(IDENTITY,[request],CTX,provider=provider([selected,other]))
 assert out['results'][0]['file']['content_hash']==request['expected_content_hash']
 with pytest.raises(CacheError,match='cache_file_receipt_key_unavailable'):
  find_completed_bulk(IDENTITY,[MEMBER],CTX,provider=provider([selected,other]))

def test_bulk_lookup_finds_successful_prefix_inside_one_partial_batch_plan():
 row,binding=batch_record()
 members=[MEMBER,{"node_key":"node-2","item_revision_uid":"rev-2","file_ref":{**REF,"file_uid":"file-2"}}]
 p=provider([],members);p.batch_records=[row]
 p.cache.repo.query_pinned=lambda *a,**kw:{"identity":binding}
 result=find_completed_bulk(binding,members,CTX,provider=p)
 assert result['missing_count']==1
 assert result['results'][0]['file']['content_hash']=='sha256:'+'c'*64
 assert result['results'][1] is None

def test_batch_receipt_lookup_works_before_optional_batch_index_migration():
 row,binding=batch_record()
 p=provider([], [MEMBER])
 p.cache.repo.query_pinned=lambda *a,**kw:{"identity":binding}
 p.batch_records=[row]
 result=find_completed_bulk(binding,[MEMBER],CTX,provider=p)
 assert result['results'][0]['file']['content_hash']=='sha256:'+'c'*64
 batch_queries=[sql for sql,_ in p.calls if 'runtime_plans' in sql and "$.capability_id" in sql]
 assert batch_queries and 'cache_file_batch_plan' not in batch_queries[0]

def test_batch_receipt_lookup_uses_generated_index_when_installed():
 row,binding=batch_record()
 p=provider([], [MEMBER]);p.has_batch_index=True
 p.cache.repo.query_pinned=lambda *a,**kw:{"identity":binding}
 p.batch_records=[row]
 result=find_completed_bulk(binding,[MEMBER],CTX,provider=p)
 assert result['results'][0]['file']['content_hash']=='sha256:'+'c'*64
 batch_queries=[sql for sql,_ in p.calls if 'runtime_plans' in sql and 'cache_file_batch_plan' in sql]
 assert batch_queries
