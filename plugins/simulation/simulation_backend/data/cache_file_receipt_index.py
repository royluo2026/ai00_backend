"""Read-only candidates derived from immutable signed plans and Outcomes.

Internal API only. Index rows are hints; find_completed reuses the member and
Outcome validator before exposing any artifact. No newest-file fallback.
"""
import base64
import json
from .cloud_model_cache_repository import CacheError,digest,canonical

TABLE='workmanship_sim_connector_runtime_plans'

def _provider(provider):
 if provider is not None:return provider
 from ..capabilities.cloud_model_cache_files import CacheFileProvider
 return CacheFileProvider()

def _scope(identity,context):
 return ('actor_gid=%s AND tenant_gid=%s AND status=\'succeeded\' AND cache_file_batch=%s AND cache_file_generation <=> %s AND cache_file_snapshot_hash <=> %s',
         (context.user_gid,context.team_gid,identity['batch_id'],identity['generation'],identity['snapshot_hash']))

def find_completed(payload,context,*,provider=None):
 """Return a revalidated completed result, None, or an explicit hash conflict.

 Expected hash chooses content; the original request's expected hash is used
 for result's admission-match validation, then actual bytes hash is compared.
 """
 provider=_provider(provider)
 _,identity,revision,reference=provider.source(payload,context)
 where,params=_scope(identity,context)
 where+=' AND cache_file_member_digest=MD5(JSON_ARRAY(%s,%s,%s,%s)) AND cache_file_node=%s AND cache_file_revision=%s AND cache_file_dataset=%s AND cache_file_uid=%s'
 member_values=(payload['node_key'],revision,reference['dataset_uid'],reference['file_uid']);params+=member_values+member_values
 expected=payload.get('expected_content_hash')
 if expected:where+=' AND cache_file_content_hash=%s';params+=(expected,)
 with provider.cache.repo.connect() as conn,conn.cursor() as c:
  c.execute(f'SELECT COUNT(DISTINCT cache_file_content_hash) AS hashes FROM {TABLE} WHERE {where}',params)
  count=c.fetchone()['hashes']
  if count>1:raise CacheError('cache_file_content_conflict')
  if count==0:return None
  c.execute(f'SELECT plan_id,cache_file_content_hash,cache_file_expected_content_hash FROM {TABLE} WHERE {where} AND cache_file_content_hash IS NOT NULL ORDER BY plan_id LIMIT 1',params)
  row=c.fetchone()
 result=provider.result({**payload,'expected_content_hash':row['cache_file_expected_content_hash'],'operation_id':row['plan_id']},context).data
 if result['status']!='completed' or not result.get('file') or result['file']['content_hash']!=row['cache_file_content_hash'] or (expected and result['file']['content_hash']!=expected):raise CacheError('cache_file_result_invalid')
 return result

def list_completed(batch_id,context,*,provider=None,expected_generation=None,expected_snapshot_hash=None,page_size=100,cursor=None):
 """Bounded candidate pointers only; callers must revalidate result per file.

 Cursor is fixed-identity/actor bound, not an authorization token. Full history
 is paged; hash conflicts must be resolved with find_completed before opening.
 """
 if type(page_size)!=int or not 1<=page_size<=500:raise CacheError('cache_query_invalid')
 provider=_provider(provider);provider.cache._read(batch_id,context)
 identity=provider.cache.repo.query_pinned(batch_id,context.team_gid,scope='roots',projection='structure',page_size=1,expected_generation=expected_generation,expected_snapshot_hash=expected_snapshot_hash)['identity']
 where,params=_scope(identity,context);binding=digest([identity,context.user_gid,context.team_gid]);after=None
 if cursor is not None:
  try:
   if not isinstance(cursor,str) or not 1<=len(cursor)<=2048:raise ValueError()
   v=json.loads(base64.b64decode(cursor.encode('ascii'),altchars=b'-_',validate=True))
   if set(v)!={'binding','after'} or v['binding']!=binding or not isinstance(v['after'],str) or not 1<=len(v['after'])<=256:raise ValueError()
   after=v['after']
  except (ValueError,TypeError,UnicodeError,KeyError) as exc:raise CacheError('cache_cursor_invalid') from exc
 if after:where+=' AND plan_id>%s';params+=(after,)
 with provider.cache.repo.connect() as conn,conn.cursor() as c:
  c.execute(f'SELECT plan_id,cache_file_node,cache_file_revision,cache_file_dataset,cache_file_uid,cache_file_content_hash FROM {TABLE} WHERE {where} AND cache_file_content_hash IS NOT NULL ORDER BY plan_id LIMIT %s',(*params,page_size+1));rows=c.fetchall()
 more=len(rows)>page_size;rows=rows[:page_size]
 receipts=[{'operation_id':r['plan_id'],'node_key':r['cache_file_node'],'item_revision_uid':r['cache_file_revision'],'dataset_uid':r['cache_file_dataset'],'file_uid':r['cache_file_uid'],'content_hash':r['cache_file_content_hash']} for r in rows]
 next_cursor=base64.urlsafe_b64encode(canonical({'binding':binding,'after':rows[-1]['plan_id']}).encode()).decode() if more else None
 return {'identity':identity,'receipts':receipts,'next_cursor':next_cursor,'authority':'candidate_only_validate_member_and_result'}
