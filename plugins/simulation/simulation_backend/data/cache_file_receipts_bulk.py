"""Bounded bulk member reads and cryptographically reverified file receipts.

Internal backend API. Caller supplies fixed binding and projected members;
this function still verifies every member against frozen cloud node data.
"""
import hashlib
import json
from .cloud_model_cache_repository import CacheError
from .cache_file_receipt_index import _provider,_scope,TABLE
from .cache_file_receipt_validation import validate_cached_file_result,validate_cached_file_batch_result

def _json(value):return json.loads(value) if isinstance(value,str) else value

def _key(member):
 ref=member['file_ref']
 return member['node_key'],member['item_revision_uid'],ref['dataset_uid'],ref['file_uid']

def verify_receipt_row(row,binding,member,context):
 """Verify original device signature, signed plan hash, result hash and membership.

 Current device public key must match the receipt key; missing historical key
 is an explicit failure, never silently downgraded to trusting the index.
 """
 from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2,canonicalize_v2
 from ..application.connector_protocol_v2 import OutcomeVerifier
 try:
  plan=ConnectorExecutionPlanV2.model_validate(_json(row['plan_json']))
  raw=_json(row['outcome_json'])
  signed=raw.get('original_outcome') if raw.get('record_type')=='server_reconciliation_v2' else raw
  if not isinstance(signed,dict) or signed.get('device_key_id')!=row['stored_device_key_id']:raise CacheError('cache_file_receipt_key_unavailable')
  outcome=OutcomeVerifier.verify(signed,_json(row['device_signing_jwk']))
  OutcomeVerifier.verify_steps(plan,outcome)
  if (plan.plan_id,plan.actor_id,plan.tenant_id,plan.plan_hash)!=(row['plan_id'],context.user_gid,context.team_gid,row['plan_hash']):raise CacheError('cache_file_operation_mismatch')
  if (outcome.plan_id,outcome.plan_hash,outcome.tenant_id,outcome.device_id,outcome.runtime_generation,outcome.runtime_instance_id)!=(plan.plan_id,plan.plan_hash,plan.tenant_id,plan.device_id,plan.runtime_generation,plan.runtime_instance_id):raise CacheError('cache_file_operation_mismatch')
  if outcome.overall_status!='succeeded' or hashlib.sha256(canonicalize_v2(outcome)).hexdigest()!=row['outcome_hash']:raise CacheError('cache_file_result_invalid')
  expected=plan.steps[0].payload.get('expected_content_hash')
  result=validate_cached_file_result(binding,member['node_key'],member['item_revision_uid'],member['file_ref'],expected,row['plan_id'],plan.model_dump(mode='json'),{'status':'completed','outcome':outcome.model_dump(mode='json')})
  if result['file']['content_hash']!=row['cache_file_content_hash']:raise CacheError('cache_file_result_invalid')
  return result
 except CacheError:raise
 except (ValueError,KeyError,TypeError,AttributeError) as exc:raise CacheError('cache_file_result_invalid') from exc

def verify_batch_receipt_row(row,binding,context):
 """Verify one signed batch plan and return successful member results only."""
 from backend.contracts.connector_execution_plan_v2 import ConnectorExecutionPlanV2,canonicalize_v2
 from ..application.connector_protocol_v2 import OutcomeVerifier
 try:
  plan=ConnectorExecutionPlanV2.model_validate(_json(row['plan_json']))
  raw=_json(row['outcome_json'])
  signed=raw.get('original_outcome') if raw.get('record_type')=='server_reconciliation_v2' else raw
  if not isinstance(signed,dict) or signed.get('device_key_id')!=row['stored_device_key_id']:raise CacheError('cache_file_receipt_key_unavailable')
  outcome=OutcomeVerifier.verify(signed,_json(row['device_signing_jwk']))
  OutcomeVerifier.verify_steps(plan,outcome)
  if (plan.plan_id,plan.actor_id,plan.tenant_id,plan.plan_hash)!=(row['plan_id'],context.user_gid,context.team_gid,row['plan_hash']):raise CacheError('cache_file_operation_mismatch')
  if (outcome.plan_id,outcome.plan_hash,outcome.tenant_id,outcome.device_id,outcome.runtime_generation,outcome.runtime_instance_id)!=(plan.plan_id,plan.plan_hash,plan.tenant_id,plan.device_id,plan.runtime_generation,plan.runtime_instance_id):raise CacheError('cache_file_operation_mismatch')
  if hashlib.sha256(canonicalize_v2(raw)).hexdigest()!=row['outcome_hash']:raise CacheError('cache_file_result_invalid')
  status={'succeeded':'completed','failed_without_effect':'failed','outcome_unknown':'outcome_unknown','manual_review_required':'outcome_unknown'}[outcome.overall_status]
  members=[]
  for step in plan.steps[1:]:
   payload=step.payload
   members.append({'step_id':step.step_id,'node_key':payload['node_key'],'item_revision_uid':payload['item_revision_uid'],
    'file_ref':payload['file_ref'],'expected_content_hash':payload.get('expected_content_hash')})
  result=validate_cached_file_batch_result(binding,members,row['plan_id'],plan.model_dump(mode='json'),
    {'status':status,'outcome':outcome.model_dump(mode='json')})
  return result
 except CacheError:raise
 except (ValueError,KeyError,TypeError,AttributeError) as exc:raise CacheError('cache_file_result_invalid') from exc

def find_completed_bulk(binding,members,context,*,provider=None,chunk_size=200):
 """Return aligned results/None without per-file source/count/plan calls.

 Expected content hash per member selects a version, otherwise different
 actual content hashes are an explicit conflict. Files absent from receipts
 remain None. A failed/unknown receipt is never a reusable file.
 """
 if type(chunk_size)!=int or not 1<=chunk_size<=500 or not isinstance(members,list) or len(members)>50000:raise CacheError('cache_query_invalid')
 provider=_provider(provider);cache=provider.cache
 cache._read(binding['batch_id'],context)
 identity=cache.repo.query_pinned(binding['batch_id'],context.team_gid,scope='roots',projection='structure',page_size=1,expected_generation=binding['generation'],expected_snapshot_hash=binding['snapshot_hash'])['identity']
 if identity!=binding:raise CacheError('cache_snapshot_mismatch')
 try:
  grouped={}
  for m in members:grouped.setdefault(_key(m),[]).append(m)
 except (KeyError,TypeError,AttributeError) as exc:raise CacheError('cache_file_not_referenced') from exc
 node_keys=list(dict.fromkeys(k[0] for k in grouped));frozen={}
 with cache.repo.connect() as conn,conn.cursor() as c:
  for offset in range(0,len(node_keys),chunk_size):
   keys=node_keys[offset:offset+chunk_size];placeholders=','.join(['%s']*len(keys))
   c.execute("SELECT node_key,JSON_EXTRACT(data_json,'$.structure.item_revision_uid') AS revision_json,JSON_EXTRACT(data_json,REPLACE(JSON_UNQUOTE(JSON_SEARCH(data_json,'one','IMAN_Rendering',NULL,'$.properties_result.raw_fields[*].field')),'.field','')) AS geometry_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND snapshot_generation <=> %s AND node_key IN ("+placeholders+")",(binding['batch_id'],binding['generation'],*keys))
   for row in c.fetchall():
    field=_json(row['geometry_json'])
    if not isinstance(field,dict) or field.get('field')!='IMAN_Rendering' or field.get('read_state')!='value':raise CacheError('cache_file_references_unavailable')
    frozen[row['node_key']]=(_json(row['revision_json']),_json(field['value_json']))
  for key,items in grouped.items():
   stored=frozen.get(key[0])
   if not stored or stored[0]!=key[1] or not isinstance(stored[1],list):raise CacheError('cache_file_not_referenced')
   refs=[r for r in stored[1] if isinstance(r,dict) and r.get('dataset_uid')==key[2] and r.get('file_uid')==key[3] and r.get('relation_type')=='IMAN_Rendering' and r.get('file_name','').lower().endswith('.jt')]
   if len(refs)!=1 or any(m['file_ref']!=refs[0] for m in items):raise CacheError('cache_file_not_referenced')
  matches={};keys=list(grouped)
  where,scope_params=_scope(binding,context)
  for name in ('actor_gid','tenant_gid','status','cache_file_batch','cache_file_generation','cache_file_snapshot_hash'):where=where.replace(name,'p.'+name)
  import pymysql.cursors
  with conn.cursor(pymysql.cursors.SSDictCursor) as stream:
   for offset in range(0,len(keys),chunk_size):
    chunk=keys[offset:offset+chunk_size];buckets=','.join(['MD5(JSON_ARRAY(%s,%s,%s,%s))']*len(chunk));values=tuple(v for key in chunk for v in key)
    stream.execute("SELECT p.plan_id,p.plan_json,p.outcome_json,p.plan_hash,p.outcome_hash,p.cache_file_node,p.cache_file_revision,p.cache_file_dataset,p.cache_file_uid,p.cache_file_content_hash,d.device_signing_jwk,d.device_key_id AS stored_device_key_id FROM "+TABLE+" p LEFT JOIN workmanship_sim_connector_runtime_devices d ON d.device_id=p.device_id WHERE "+where+" AND p.protocol='ai00.connector.execution-plan.v2' AND p.cache_file_member_digest IN ("+buckets+") AND p.cache_file_content_hash IS NOT NULL ORDER BY p.plan_id",(*scope_params,*values))
    while rows:=stream.fetchmany(100):
     for row in rows:
      key=tuple(row[k] for k in ['cache_file_node','cache_file_revision','cache_file_dataset','cache_file_uid'])
      if key not in grouped:continue # bucket collisions are not membership
      wanted={m.get('expected_content_hash') for m in grouped[key]}
      if None not in wanted and row['cache_file_content_hash'] not in wanted:continue
      result=verify_receipt_row(row,binding,grouped[key][0],context)
      versions=matches.setdefault(key,{})
      versions.setdefault(result['file']['content_hash'],result) # deterministic first op, not latest
  # A batch plan is indexed once by its fixed cache binding; at most eight
  # members are parsed from each row after the device-signed Outcome verifies.
  with conn.cursor() as schema_cursor:
   schema_cursor.execute(f'SHOW COLUMNS FROM {TABLE}',())
   columns={row.get('Field') if isinstance(row,dict) else row[0] for row in schema_cursor.fetchall()}
  indexed={'cache_file_batch_plan','cache_file_batch_generation','cache_file_batch_snapshot_hash'}<=columns
  if indexed:
   batch_where,batch_params=_scope(binding,context)
   for name in ('actor_gid','tenant_gid','status','cache_file_batch','cache_file_generation','cache_file_snapshot_hash'):
    batch_where=batch_where.replace(name,'p.'+name)
   batch_where=batch_where.replace("p.status='succeeded'","p.status IN ('succeeded','failed_without_effect','outcome_unknown','manual_review_required')")
   batch_where=batch_where.replace('p.cache_file_batch','p.cache_file_batch_plan')
   batch_where=batch_where.replace('p.cache_file_generation','p.cache_file_batch_generation')
   batch_where=batch_where.replace('p.cache_file_snapshot_hash','p.cache_file_batch_snapshot_hash')
  else:
   # Keep receipt discovery correct before the optional 0035 index migration.
   batch_where=("p.actor_gid=%s AND p.tenant_gid=%s AND p.status IN "
    "('succeeded','failed_without_effect','outcome_unknown','manual_review_required') "
    "AND p.protocol=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(p.plan_json,'$.capability_id'))=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(p.plan_json,'$.steps[0].operation_id'))=%s "
    "AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.plan_json,'$.steps[0].payload.identity.batch_id')),'null') <=> %s "
    "AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.plan_json,'$.steps[0].payload.identity.generation')),'null') <=> %s "
    "AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.plan_json,'$.steps[0].payload.identity.snapshot_hash')),'null') <=> %s")
   batch_params=(context.user_gid,context.team_gid,'ai00.connector.execution-plan.v2',
    'simulation.model_cache.file.fetch.batch.request','teamcenter.model_files.size.preflight@1',
    binding['batch_id'],binding.get('generation'),binding.get('snapshot_hash'))
  with conn.cursor(pymysql.cursors.SSDictCursor) as stream:
   stream.execute("SELECT p.plan_id,p.plan_json,p.outcome_json,p.plan_hash,p.outcome_hash,d.device_signing_jwk,d.device_key_id AS stored_device_key_id FROM "+TABLE+" p LEFT JOIN workmanship_sim_connector_runtime_devices d ON d.device_id=p.device_id WHERE "+batch_where+" AND p.protocol='ai00.connector.execution-plan.v2' ORDER BY p.plan_id",batch_params)
   while rows:=stream.fetchmany(100):
    for row in rows:
     # An expired plan can be outcome_unknown without ever returning an Outcome.
     # It supplies no reusable file; do not confuse absence with a corrupt receipt.
     if row['outcome_json'] is None:continue
     result=verify_batch_receipt_row(row,binding,context)
     for item in result['files']:
      if item['status']!='succeeded' or not item.get('file'):continue
      key=(item['node_key'],item['item_revision_uid'],item['file_ref']['dataset_uid'],item['file_ref']['file_uid'])
      if key not in grouped:continue
      wanted={m.get('expected_content_hash') for m in grouped[key]}
      content_hash=item['file']['content_hash']
      if None not in wanted and content_hash not in wanted:continue
      versions=matches.setdefault(key,{})
      versions.setdefault(content_hash,{'operation_id':result['operation_id'],'identity':identity,'node_key':item['node_key'],
       'item_revision_uid':item['item_revision_uid'],'file_ref':item['file_ref'],'status':'completed','file':item['file'],'error_code':None})

 results=[]
 for member in members:
  versions=matches.get(_key(member),{});expected=member.get('expected_content_hash')
  if expected:result=versions.get(expected)
  elif len(versions)>1:raise CacheError('cache_file_content_conflict')
  else:result=next(iter(versions.values()),None)
  results.append(result)
 return {'identity':identity,'results':results,'missing_count':sum(r is None for r in results)}
