"""Owner-scoped desktop contracts; published legacy descriptors stay immutable."""
from __future__ import annotations

import json
import os
from jsonschema import Draft202012Validator
from backend.capability_v2.contracts import BusinessInvariantContract, ExposurePolicy, ResourceSelector
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec
from backend.platform_sdk.request_credentials import downstream_runtime_credential
from .contracts import obj
from .provider import descriptor_for, write_output
from ..data.connection import close_agent_transaction, rollback_agent_transaction

TEXT = {'type': 'string', 'maxLength': 65536}
SHORT = {'type': 'string', 'maxLength': 4096}
ID = {'type': 'string', 'minLength': 1, 'maxLength': 256}
BOOL = {'type': 'boolean'}


def array(item, maximum=128):
    return {'type':'array', 'items':item, 'maxItems':maximum}


PARAMS = obj({key: SHORT for key in ('agent_name','note','assignee','task_desc','tool_name','params_hint','confirm_required','skill_gid','skill_name','branches','strategy','condition_expr','true_branch','false_branch','domain','list_gid','item_query','table','db','access','var_name','scope','path','format','approver')})
PARAMS['properties']['_items'] = array(obj({key:SHORT for key in ('gid','title','name','item_type','status','url','description')}))
CANVAS = obj({
    'title': SHORT, 'lanes': array(obj({'id':ID, 'label':SHORT}, ('id','label'))),
    'steps': {'type':'integer','minimum':0,'maximum':128}, 'step_labels': array(SHORT),
    'nodes': array(obj({'id':ID,'type':{'enum':['agent','human','tool_read','tool_write','skill_call','fork','join','condition','list','data_db','data_mem','data_file','human_approval','human_task','result_list']},'label':SHORT,'lane_id':SHORT,'laneIdx':{'type':'integer','minimum':0,'maximum':127},'step':{'type':'integer','minimum':0,'maximum':127},'params':PARAMS,'x':{'type':'number'},'y':{'type':'number'}}, ('id','type','label','params'))),
    'connections': array(obj({key:SHORT for key in ('id','from','to','type','fromPort','toPort')}, ('id','from','to','type')), 256),
    'questions': array(obj({key:SHORT for key in ('id','nodeId','text','answer')}, ('id','text','answer'))),
})
SCALAR = {'type':['string','number','boolean','null']}
# A bounded JSON Schema document is data with a finite vocabulary. Property
# names may vary; every property definition follows this same closed grammar.
SCHEMA_DOCUMENT = obj({'type':{'enum':['object','array','string','number','integer','boolean','null']},'title':SHORT,'description':SHORT,
    'properties':{'type':'object','maxProperties':64,'patternProperties':{'^[A-Za-z][A-Za-z0-9_.-]{0,127}$':{'$ref':'#/$defs/parameter_schema'}},'additionalProperties':False},
    'required':array(ID,64),'items':{'$ref':'#/$defs/parameter_schema'},'enum':array(SCALAR,64),'default':SCALAR,
    'minimum':{'type':'number'},'maximum':{'type':'number'},'minLength':{'type':'integer','minimum':0},'maxLength':{'type':'integer','minimum':0,'maximum':65536},
    'minItems':{'type':'integer','minimum':0},'maxItems':{'type':'integer','minimum':0,'maximum':128},'additionalProperties':{'const':False},'format':SHORT})
CONTENT = obj({'template':TEXT,'variables':array(obj({'name':ID,'label':SHORT,'required':BOOL,'default':SHORT},('name','label','required','default')),64),
    'system_hint':TEXT,'script':TEXT,'input_schema':{'$ref':'#/$defs/parameter_schema'},'description':SHORT,'need_confirm':BOOL,'flow_gid':SHORT,'canvas':CANVAS})
CREATE = obj({'name':{'type':'string','pattern':'^[a-z][a-z0-9_]{1,49}$'},'title':ID,'description':SHORT,'skill_type':{'enum':['prompt','tool','flow']},
    'visibility':{'enum':['private','team','global']},'content':CONTENT,'icon':SHORT,'tags':array(ID,64),'sort_order':{'type':'integer'}},('name','title','skill_type','content'))
CREATE['$defs'] = {'parameter_schema':SCHEMA_DOCUMENT}
UPDATE = obj({'skill_gid':ID,'changes':obj({**{key:value for key,value in CREATE['properties'].items() if key not in ('name','skill_type')},
    'status':{'enum':['draft','active','disabled']},'is_pinned':BOOL})},('skill_gid','changes'))
UPDATE['properties']['changes']['minProperties'] = 1
UPDATE['$defs'] = CREATE['$defs']
SKILL_RESULT = obj({'success':{'const':True},'gid':ID},('success',))
CHAT_CONTEXT = obj({key:TEXT for key in ('text','current_page','project_name','canvas_context','bottom_context')})
CHAT = obj({'operation':{'enum':['chat_stream','chat_sync']},'body':obj({'message':TEXT,'session_id':{'type':['string','null'],'maxLength':256},'context':CHAT_CONTEXT},('message',))},('operation','body'))
CHAT_RESULT = obj({'data':obj({'stream_id':{'type':'string','pattern':'^capability-stream-[0-9a-f]{32}$'},'media_type':SHORT,'response_json':{'type':'string','maxLength':1048576}})},('data',))
SESSION = obj({key:SHORT for key in ('gid','title','created_at','updated_at')},('gid','title','created_at','updated_at'))
LOG = obj({**{key:TEXT for key in ('gid','session_gid','user_gid','tool_name','inputs_json','result_json','resource_gid','resource_type','status','created_at')},'id':{'type':'integer'},'is_write':BOOL,'is_confirmed':BOOL})
AUDIT_QUERY = obj({**{key:SHORT for key in ('session_gid','user_gid','tool_name')},'is_write':{'enum':['','true','false']},'limit':{'type':'integer','minimum':1,'maximum':500},'offset':{'type':'integer','minimum':0}})
TOOL = obj({'name':ID,'description':TEXT,'category':SHORT,'need_confirm':BOOL,'params':array(ID,64)},('name','description','category','need_confirm','params'))
TOOLS = obj({**{key:array(TOOL,500) for key in ('read','write_confirm','write_no_confirm','system')},'total':{'type':'integer','minimum':0}},('read','write_confirm','write_no_confirm','system','total'))
CONFIG = obj({'source':SHORT,'model':SHORT,'api_base':SHORT,'has_key':BOOL,'key_preview':SHORT,'is_admin':BOOL})


async def chat(payload, context):
    from .interaction_chat_change import apply_interaction_chat_change
    body = dict(payload['body'])
    body['context_json'] = json.dumps(body.pop('context', {}), ensure_ascii=False)
    # Only the authenticated request adapter supplies this downstream credential.
    return await apply_interaction_chat_change({'operation':payload['operation'],'body':body,'ai00_token':downstream_runtime_credential()}, context)


def runtime_config_set(payload, context):
    if 'super_admin' not in set(context.active_roles):
        raise CapabilityBusinessError('permission_denied', 'Only super administrators may change runtime configuration.')
    if os.getenv('ALLOW_LOCAL_RUNTIME_SECRET_ADMIN') != '1':
        raise CapabilityBusinessError('permission_denied', 'Runtime secret administration is disabled by deployment policy.')
    from ..infrastructure.runtime_secret_store import runtime_secret_store
    store = runtime_secret_store()
    current = store.load()
    key = payload.get('api_key') or current.get('api_key', '')
    if not key:
        raise CapabilityBusinessError('invalid_input', 'A runtime API key is required.')
    store.save({'model':payload['model'],'api_base':payload.get('api_base',''),'api_key':key})
    return {'source':'local_secret','model':payload['model'],'api_base':payload.get('api_base',''),'has_key':True,'key_preview':'','is_admin':True}


def runtime_test(_payload, context):
    from ..routers.ai_chat import test_connection
    result = test_connection({}, _user={'gid':context.user_gid})
    return {'success':bool(result.get('success')),'reply':str(result.get('reply',''))[:80],
            'model':str(result.get('model',''))[:200], 'error':'' if result.get('success') else str(result.get('error') or 'Runtime connection unavailable')[:500]}


def skill_fields(payload):
    fields = dict(payload)
    if 'visibility' in fields:
        fields['scope'] = fields.pop('visibility')
    return fields


# These are exact wrappers around the actual Agent application/repository.
DEFINITIONS = (
    ('agent.skill.create',1,CREATE,SKILL_RESULT,True,'agent.interact','Creates one owned Skill with a named prompt, tool, flow or canvas content model.','agent.skill.change.apply',lambda p:{'operation':'create',**skill_fields(p)}),
    ('agent.skill.update',1,UPDATE,SKILL_RESULT,True,'agent.interact','Updates one owned Skill while preserving system Skill and global publishing restrictions.','agent.skill.change.apply',lambda p:{'operation':'update','skill_gid':p['skill_gid'],**skill_fields(p['changes'])}),
    ('agent.session.list',1,obj({}),obj({'sessions':array(SESSION,50)},('sessions',)),False,'agent.read','Lists the latest 50 conversations owned by the authenticated user.','agent.session.read',lambda p:{'operation':'list'}),
    ('agent.audit.search',1,AUDIT_QUERY,obj({'logs':array(LOG,500),'total':{'type':'integer','minimum':0},'limit':{'type':'integer'},'offset':{'type':'integer'}},('logs','total','limit','offset')),False,'agent.read','Returns a bounded administrator-only Agent audit result.','agent.audit.read',lambda p:p),
    ('agent.tool_catalog.list',1,obj({}),TOOLS,False,'agent.read','Lists the finite tool descriptions shown in the Agent toolbox.','agent.tool_catalog.read',lambda p:{'operation':'list'}),
    ('agent.flow.capability_manifest.get',1,obj({}),obj({'manifest':{'type':'array','maxItems':0},'message':SHORT},('manifest','message')),False,'agent.read','Reports the retired legacy node palette and the requirement to select governed Catalog capabilities.','agent.flow.read',lambda p:{'operation':'manifest'}),
    ('agent.interaction.cancel',2,obj({'session_gid':ID},('session_gid',)),obj({'ok':{'const':True},'session_gid':ID},('ok','session_gid')),True,'agent.interact','Cancels the current interaction only in a session owned by the authenticated user.','agent.interaction.cancel',lambda p:p),
    ('agent.runtime.config.set',1,obj({'model':{**ID,'maxLength':200},'api_base':{**SHORT,'maxLength':500},'api_key':{'type':'string','maxLength':8192}},('model',)),CONFIG,True,'system.tech_config','Replaces explicitly enabled deployment runtime settings without returning the secret.',None,None),
    ('agent.runtime.connection.test',1,obj({}),obj({'success':BOOL,'reply':{'type':'string','maxLength':80},'model':{'type':'string','maxLength':200},'error':SHORT},('success','reply','model','error')),False,'agent.interact','Runs a bounded fixed model connectivity probe and returns a normalized diagnostic.',None,None),
)


def _descriptor(spec, effect):
    return descriptor_for(spec).model_copy(update={'exposure':ExposurePolicy(web=True,api=True,plugin=False,agent=False,mcp=False),
        'business_effect':effect,'business_acceptance_criteria':(effect,'Only closed request and response models cross the Gateway; the application derives owner and tenant.'),
        'business_invariants':(BusinessInvariantContract(rule_id=spec.id+'.actor_bound',version=1,statement='The application derives the owner and tenant from authenticated context.',
            applies_when='the desktop action executes',enforcement_ref='plugins/agent/agent_backend/application/service.py:invoke',error_code='permission_denied',test_refs=('backend/tests/test_desktop_round5_agent.py',)),),
        'no_business_invariant_reason':None, 'evidence_policy':'optional','idempotency_policy':'required' if spec.risk.value!='read' else 'none'})


def register_desktop_agent_capabilities(registry, provider, transaction_factory):
    for capability_id,version,input_schema,output_schema,write,permission,effect,legacy,adapt in DEFINITIONS:
        request_validator, result_validator = Draft202012Validator(input_schema), Draft202012Validator(output_schema)
        def handler(payload, context, _id=capability_id, _version=version, _write=write, _legacy=legacy, _adapt=adapt, _input=request_validator, _output=result_validator):
            if not _input.is_valid(payload):
                raise CapabilityBusinessError('invalid_input','The request does not match this Agent action.')
            transaction = transaction_factory() if _write else None
            try:
                result = (provider.invoke(_legacy,_adapt(payload),context) if _legacy else runtime_config_set(payload,context) if _id=='agent.runtime.config.set' else runtime_test(payload,context))
                if _id == 'agent.session.list':
                    result = {'sessions':[row for row in result['sessions'] if '_sub_' not in row['gid']]}
                if not _output.is_valid(result):
                    raise CapabilityBusinessError('provider_error','The Agent result does not match its declared model.')
                if not _write:
                    return result
                output = write_output(_id,result,context)
                transaction.record_outbox(_id,_version,context,output)
                transaction.commit()
                return output
            except BaseException:
                if transaction is not None:
                    rollback_agent_transaction(transaction)
                raise
            finally:
                if transaction is not None:
                    close_agent_transaction(transaction)
        spec=CapabilitySpec(id=capability_id,version=version,owner='agent',description=effect,use_when=effect,do_not_use_when='Another business effect is requested.',
            risk='write' if write else 'read',confirmation='none' if capability_id in ('agent.interaction.cancel','agent.runtime.connection.test') else 'user' if write else 'none',
            idempotent=True,permissions=(permission,),input_schema=input_schema,output_schema=output_schema,tags=('agent','desktop','closed'))
        registry.register(spec,handler,descriptor=_descriptor(spec,effect))
    effect='Continues one authenticated user conversation with bounded sync output or a Gateway-owned stream and governed downstream tool confirmation.'
    spec=CapabilitySpec(id='agent.interaction.chat.change.apply',version=3,owner='agent',description=effect,use_when=effect,do_not_use_when='Directly executing a proposed tool.',risk='write',confirmation='none',idempotent=False,permissions=('agent.interact',),input_schema=CHAT,output_schema=CHAT_RESULT,tags=('agent','desktop','stream'))
    descriptor=_descriptor(spec,effect).model_copy(update={'resource_selectors':(ResourceSelector(resource_type='agent-session',payload_path='body.session_id',required=False),)})
    registry.register(spec,chat,descriptor=descriptor)
