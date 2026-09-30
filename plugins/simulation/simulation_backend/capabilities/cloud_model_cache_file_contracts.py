"""Shared closed file acquisition contracts, independent of providers."""
from .connector_contracts import obj,ARTIFACT_REF,TC_GEOMETRY_REF,TC_VISUALIZATION_SOURCE_SELECTOR

TEXT={'type':'string','minLength':1,'maxLength':512}
BID={'type':'string','pattern':'^[a-f0-9]{32}$'}
PIN={'type':['string','null'],'pattern':'^sha256:[a-f0-9]{64}$'}
HASH={'type':'string','pattern':'^sha256:[a-f0-9]{64}$'}
GENERATION={'type':['string','null'],'pattern':'^[a-f0-9]{32}$'}
IDENTITY=obj({'batch_id':BID,'generation':GENERATION,'snapshot_hash':PIN,'schema_version':{'const':1,'type':'integer'}},('batch_id','generation','snapshot_hash','schema_version'))
REQUEST=obj({'batch_id':BID,'node_key':TEXT,'dataset_uid':TEXT,'file_uid':TEXT,'expected_generation':GENERATION,'expected_snapshot_hash':PIN,'expected_content_hash':PIN},('batch_id','node_key','dataset_uid','file_uid'))
FILE_INPUT=obj({**IDENTITY['properties'],'node_key':TEXT,'item_revision_uid':TEXT,'source_selector':TC_VISUALIZATION_SOURCE_SELECTOR,'file_ref':TC_GEOMETRY_REF,'expected_content_hash':PIN,'artifact_resource_refs':{'type':'array','maxItems':2,'items':TEXT}},(*IDENTITY['required'],'node_key','item_revision_uid','source_selector','file_ref','expected_content_hash','artifact_resource_refs'))
FILE_OUTPUT=obj({'identity':IDENTITY,'node_key':TEXT,'item_revision_uid':TEXT,'file_ref':TC_GEOMETRY_REF,'artifact_ref':ARTIFACT_REF,'content_hash':HASH,'byte_length':{'type':'integer','minimum':24,'maximum':512*1024*1024},'acquired_at':TEXT,'captured_bytes_verified':{'const':False,'type':'boolean'}},('identity','node_key','item_revision_uid','file_ref','artifact_ref','content_hash','byte_length','acquired_at','captured_bytes_verified'))
FILE_CONTRACT={'id':'teamcenter.model_file.fetch@1','input':FILE_INPUT,'output':FILE_OUTPUT}
ADMISSION=obj({'operation_id':TEXT,'identity':IDENTITY,'node_key':TEXT,'item_revision_uid':TEXT,'file_ref':TC_GEOMETRY_REF,'status':{'type':'string','enum':['queued','running','completed','failed','outcome_unknown','cancelled','leased','pending','executing','expired','reconciling','failed_without_effect','manual_review_required']}},('operation_id','identity','node_key','item_revision_uid','file_ref','status'))
RESULT=obj({**ADMISSION['properties'],'file':{'anyOf':[FILE_OUTPUT,{'type':'null'}]},'error_code':{'type':['string','null']}},(*ADMISSION['required'],'file','error_code'))

BATCH_MEMBER=obj({'node_key':TEXT,'dataset_uid':TEXT,'file_uid':TEXT,'expected_content_hash':PIN},('node_key','dataset_uid','file_uid'))
BATCH_FILES={'type':'array','minItems':1,'maxItems':8,'items':BATCH_MEMBER}
BATCH_REQUEST=obj({'batch_id':BID,'expected_generation':GENERATION,'expected_snapshot_hash':PIN,'files':BATCH_FILES},('batch_id','files'))
BATCH_MEMBER_IDENTITY=obj({'step_id':TEXT,'node_key':TEXT,'item_revision_uid':TEXT,'file_ref':TC_GEOMETRY_REF},('step_id','node_key','item_revision_uid','file_ref'))
BATCH_MEMBER_ADMISSION=obj({**BATCH_MEMBER_IDENTITY['properties']},BATCH_MEMBER_IDENTITY['required'])
BATCH_ADMISSION=obj({'operation_id':TEXT,'identity':IDENTITY,'status':ADMISSION['properties']['status'],'files':{'type':'array','minItems':1,'maxItems':8,'items':BATCH_MEMBER_ADMISSION}},('operation_id','identity','status','files'))
STEP_STATUS={'type':'string','enum':['succeeded','failed_without_effect','outcome_unknown','manual_review_required']}
PREFLIGHT_FILE=obj({**BATCH_MEMBER_IDENTITY['properties'],'file_size':{'type':'integer','minimum':1,'maximum':9007199254740991}},(*BATCH_MEMBER_IDENTITY['required'],'file_size'))
PREFLIGHT_RESULT=obj({'identity':IDENTITY,'files':{'type':'array','minItems':1,'maxItems':8,'items':PREFLIGHT_FILE},'total_byte_length':{'type':'integer','minimum':0,'maximum':9007199254740991},'error_code':{'type':['string','null']}},('identity','files','total_byte_length','error_code'))
PREFLIGHT_INPUT_FILE=obj({**BATCH_MEMBER_IDENTITY['properties'],'expected_content_hash':PIN},(*BATCH_MEMBER_IDENTITY['required'],))
PREFLIGHT_INPUT=obj({'identity':IDENTITY,'source_selector':TC_VISUALIZATION_SOURCE_SELECTOR,'files':{'type':'array','minItems':1,'maxItems':8,'items':PREFLIGHT_INPUT_FILE}},('identity','source_selector','files'))
PREFLIGHT_CONTRACT={'id':'teamcenter.model_files.size.preflight@1','input':PREFLIGHT_INPUT,'output':PREFLIGHT_RESULT}
BATCH_MEMBER_RESULT=obj({**BATCH_MEMBER_IDENTITY['properties'],'expected_content_hash':PIN,'status':STEP_STATUS,'file':{'anyOf':[FILE_OUTPUT,{'type':'null'}]},'file_size':{'type':['integer','null'],'minimum':1,'maximum':9007199254740991},'error_code':{'type':['string','null']},'not_attempted':{'type':'boolean'}},(*BATCH_MEMBER_IDENTITY['required'],'expected_content_hash','status','file','file_size','error_code','not_attempted'))
BATCH_PREFLIGHT_SUMMARY=obj({'status':STEP_STATUS,'error_code':{'type':['string','null']},'total_byte_length':{'type':['integer','null'],'minimum':0,'maximum':9007199254740991}},('status','error_code','total_byte_length'))
BATCH_PLAN_STATUS={'type':'string','enum':['queued','running','completed','failed','outcome_unknown','cancelled','leased','pending','executing','expired','reconciling','failed_without_effect','manual_review_required']}
BATCH_RESULT_INPUT=obj({**BATCH_REQUEST['properties'],'operation_id':TEXT},(*BATCH_REQUEST['required'],'operation_id'))
BATCH_RESULT=obj({'operation_id':TEXT,'identity':IDENTITY,'plan_status':BATCH_PLAN_STATUS,'preflight':{'anyOf':[BATCH_PREFLIGHT_SUMMARY,{'type':'null'}]},'files':{'type':'array','maxItems':8,'items':BATCH_MEMBER_RESULT}},('operation_id','identity','plan_status','preflight','files'))
