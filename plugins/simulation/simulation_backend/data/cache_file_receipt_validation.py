"""Shared single/bulk exact admission and file-result validation."""
from .cloud_model_cache_repository import CacheError

# Previously issued, signed 100 MiB plans remain readable after raising the
# current file limit. Never apply the new limit to their historical receipts.
LEGACY_FILE_CONTRACT_HASH='sha256:145095d2e61f01abbae90108229dc58b8a563c03f6bb9e555f66d0921a1ce8e9'

def validate_cached_file_result(identity,node_key,revision,reference,expected_hash,operation_id,plan,operation):
 from ..capabilities.cloud_model_cache_file_contracts import FILE_OUTPUT
 from backend.capabilities.validation_next import validate_payload
 steps=plan.get('steps',[])
 if plan.get('capability_id')!='simulation.model_cache.file.fetch.request' or len(steps)!=1 or steps[0]['operation_id']!='teamcenter.model_file.fetch@1':raise CacheError('cache_file_operation_mismatch')
 admitted=steps[0]['payload']
 if any(admitted.get(key)!=value for key,value in {**identity,'node_key':node_key,'item_revision_uid':revision,'file_ref':reference,'expected_content_hash':expected_hash}.items()):raise CacheError('cache_file_operation_mismatch')
 status=operation['status'];outcome_steps=(operation.get('outcome') or {}).get('steps') or []
 result=outcome_steps[-1].get('result') if outcome_steps and status=='completed' else None
 if result is not None:
  validate_payload(FILE_OUTPUT,result,label='file')
  if result['identity']!=identity or result['file_ref']!=reference or result['node_key']!=node_key or result['item_revision_uid']!=revision or result['content_hash']!='sha256:'+result['artifact_ref']['sha256'] or result['byte_length']!=result['artifact_ref']['byte_size'] or result['artifact_ref']['media_type']!='model/jt' or (admitted.get('expected_content_hash') and result['content_hash']!=admitted['expected_content_hash']):raise CacheError('cache_file_result_invalid')
 if status=='completed' and result is None:raise CacheError('cache_file_result_invalid')
 return {'operation_id':operation_id,'identity':identity,'node_key':node_key,'item_revision_uid':revision,'file_ref':reference,'status':status,'file':result,'error_code':outcome_steps[-1].get('error_code') if outcome_steps else None}


def validate_cached_file_batch_result(identity,members,operation_id,plan,operation):
 """Validate a signed preflight/fetch plan and preserve each exact member outcome."""
 from ..capabilities.cloud_model_cache_file_contracts import FILE_OUTPUT,PREFLIGHT_RESULT
 from ..capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
 from backend.capabilities.validation_next import validate_payload
 steps=plan.get('steps',[])
 preflight_operation,preflight_contract=DIRECT_VISMOCKUP_OPERATIONS['tc_file_preflight']
 fetch_operation,fetch_contract=DIRECT_VISMOCKUP_OPERATIONS['tc_file']
 admitted_fetch_contract=steps[1].get('contract_hash') if len(steps)>1 else None
 if admitted_fetch_contract not in (fetch_contract,LEGACY_FILE_CONTRACT_HASH):raise CacheError('cache_file_operation_mismatch')
 if (plan.get('plan_id')!=operation_id or plan.get('capability_id')!='simulation.model_cache.file.fetch.batch.request'
     or len(steps)!=len(members)+1 or not steps or steps[0].get('step_id')!='step-00001'
     or steps[0].get('operation_id')!=preflight_operation or steps[0].get('contract_hash')!=preflight_contract
     or steps[0].get('depends_on')!=[]):
  raise CacheError('cache_file_operation_mismatch')
 expected_preflight=[]
 for index,member in enumerate(members,start=2):
  step_id=f'step-{index:05d}'
  expected_preflight.append({'step_id':step_id,'node_key':member['node_key'],'item_revision_uid':member['item_revision_uid'],
   'file_ref':member['file_ref'],'expected_content_hash':member.get('expected_content_hash')})
 preflight_payload=steps[0].get('payload') or {}
 if preflight_payload.get('identity')!=identity or preflight_payload.get('files')!=expected_preflight:
  raise CacheError('cache_file_operation_mismatch')
 for index,(step,member) in enumerate(zip(steps[1:],members),start=2):
  payload=step.get('payload') or {}
  step_id=f'step-{index:05d}'
  if (step.get('step_id')!=step_id or step.get('operation_id')!=fetch_operation or step.get('contract_hash')!=admitted_fetch_contract
      or step.get('depends_on')!=['step-00001']):
   raise CacheError('cache_file_operation_mismatch')
  expected={**identity,'node_key':member['node_key'],'item_revision_uid':member['item_revision_uid'],'file_ref':member['file_ref'],
   'expected_content_hash':member.get('expected_content_hash'),'artifact_resource_refs':['simulation://model-cache/'+identity['batch_id']]}
  if 'source_selector' in payload:expected['source_selector']=preflight_payload.get('source_selector')
  if payload!=expected:raise CacheError('cache_file_operation_mismatch')
 status=operation.get('status')
 outcome=operation.get('outcome') or {}
 outcome_steps=outcome.get('steps') or []
 # Historical malformed plans may still report their no-effect failures so the
 # consumer can retry. They cannot establish a successful file receipt.
 if any(row.get('status')=='succeeded' and 'source_selector' not in step.get('payload',{})
        for step,row in zip(steps[1:],outcome_steps[1:])):raise CacheError('cache_file_operation_mismatch')
 terminal={'completed','failed','outcome_unknown','manual_review_required','cancelled','expired'}
 if status not in terminal:
  return {'operation_id':operation_id,'identity':identity,'plan_status':status,'preflight':None,'files':[]}
 if not outcome_steps:
  if status in ('cancelled','expired','failed'):
   return {'operation_id':operation_id,'identity':identity,'plan_status':status,'preflight':None,
    'files':[{'step_id':f'step-{index+2:05d}','node_key':member['node_key'],'item_revision_uid':member['item_revision_uid'],
     'file_ref':member['file_ref'],'expected_content_hash':member.get('expected_content_hash'),'status':'failed_without_effect',
     'file':None,'file_size':None,'error_code':status,'not_attempted':True} for index,member in enumerate(members)]}
  raise CacheError('cache_file_result_invalid')
 outcome_status=outcome.get('overall_status')
 mapped={'succeeded':'completed','failed_without_effect':'failed','outcome_unknown':'outcome_unknown','manual_review_required':'outcome_unknown'}.get(outcome_status)
 if mapped!=status or outcome.get('plan_id')!=operation_id or outcome.get('plan_hash')!=plan.get('plan_hash'):
  raise CacheError('cache_file_operation_mismatch')
 if len(outcome_steps)>len(steps) or [row.get('step_id') for row in outcome_steps]!=[row.get('step_id') for row in steps[:len(outcome_steps)]]:
  raise CacheError('cache_file_result_invalid')
 preflight_step=outcome_steps[0]
 preflight_status=preflight_step.get('status')
 preflight_data=preflight_step.get('result')
 preflight=None;size_by_step={}
 if preflight_data is not None:
  try:validate_payload(PREFLIGHT_RESULT,preflight_data,label='preflight')
  except Exception as exc:raise CacheError('cache_file_result_invalid') from exc
  expected_files=[]
  for index,member in enumerate(members,start=2):
   expected_files.append({'step_id':f'step-{index:05d}','node_key':member['node_key'],'item_revision_uid':member['item_revision_uid'],'file_ref':member['file_ref']})
  actual=[{key:value for key,value in item.items() if key in ('step_id','node_key','item_revision_uid','file_ref')} for item in preflight_data['files']]
  if preflight_data['identity']!=identity or actual!=expected_files:
   raise CacheError('cache_file_operation_mismatch')
  size_by_step={item['step_id']:item['file_size'] for item in preflight_data['files']}
  if sum(size_by_step.values())!=preflight_data['total_byte_length']:
   raise CacheError('cache_file_result_invalid')
  byte_limit=(512 if len(members)==1 and admitted_fetch_contract==fetch_contract else 100)*1024*1024
  if preflight_status=='succeeded' and (preflight_data['error_code'] is not None or preflight_data['total_byte_length']>byte_limit):
   raise CacheError('cache_file_result_invalid')
  if preflight_status=='failed_without_effect' and not preflight_data['error_code']:
   raise CacheError('cache_file_result_invalid')
  if preflight_status=='failed_without_effect' and preflight_data['error_code']=='cache_file_batch_size_exceeded' and preflight_data['total_byte_length']<=byte_limit:
   raise CacheError('cache_file_result_invalid')
  preflight={'status':preflight_status,'error_code':preflight_data['error_code'],'total_byte_length':preflight_data['total_byte_length']}
 else:
  preflight={'status':preflight_status,'error_code':preflight_step.get('error_code'),'total_byte_length':None}
 if preflight_status!='succeeded':
  if len(outcome_steps)!=1:raise CacheError('cache_file_result_invalid')
  error=preflight_data.get('error_code') if isinstance(preflight_data,dict) else preflight_step.get('error_code')
  if not error:error='preflight_failed'
  results=[{'step_id':f'step-{index+2:05d}','node_key':member['node_key'],'item_revision_uid':member['item_revision_uid'],
   'file_ref':member['file_ref'],'expected_content_hash':member.get('expected_content_hash'),'status':preflight_status,
   'file':None,'file_size':size_by_step.get(f'step-{index+2:05d}'),'error_code':error,'not_attempted':True}
   for index,member in enumerate(members)]
  return {'operation_id':operation_id,'identity':identity,'plan_status':status,'preflight':preflight,'files':results}
 results_by_step={row['step_id']:row for row in outcome_steps[1:]}
 results=[];stopped=False
 for index,member in enumerate(members,start=2):
  step_id=f'step-{index:05d}';out=results_by_step.get(step_id)
  base={'step_id':step_id,'node_key':member['node_key'],'item_revision_uid':member['item_revision_uid'],'file_ref':member['file_ref'],
   'expected_content_hash':member.get('expected_content_hash'),'file_size':size_by_step.get(step_id)}
  if out is None:
   if not stopped:raise CacheError('cache_file_result_invalid')
   results.append({**base,'status':'failed_without_effect','file':None,'error_code':'not_started_after_prior_failure','not_attempted':True})
   continue
  member_status=out.get('status');file=out.get('result') if member_status=='succeeded' else None
  if member_status=='succeeded':
   if file is None:raise CacheError('cache_file_result_invalid')
   try:validate_payload(FILE_OUTPUT,file,label='file')
   except Exception as exc:raise CacheError('cache_file_result_invalid') from exc
   if (file['identity']!=identity or file['node_key']!=member['node_key'] or file['item_revision_uid']!=member['item_revision_uid']
       or file['file_ref']!=member['file_ref'] or file['content_hash']!='sha256:'+file['artifact_ref']['sha256']
       or file['byte_length']!=file['artifact_ref']['byte_size'] or file['artifact_ref']['media_type']!='model/jt'
       or file['byte_length']!=size_by_step.get(step_id)
       or (member.get('expected_content_hash') and file['content_hash']!=member['expected_content_hash'])):
    raise CacheError('cache_file_result_invalid')
   error=None;not_attempted=False
  else:
   if member_status not in ('failed_without_effect','outcome_unknown','manual_review_required') or not out.get('error_code'):
    raise CacheError('cache_file_result_invalid')
   error=out['error_code'];not_attempted=False;stopped=True
  results.append({**base,'status':member_status,'file':file,'error_code':error,'not_attempted':not_attempted})
 if status=='completed' and len(outcome_steps)!=len(steps):raise CacheError('cache_file_result_invalid')
 return {'operation_id':operation_id,'identity':identity,'plan_status':status,'preflight':preflight,'files':results}
