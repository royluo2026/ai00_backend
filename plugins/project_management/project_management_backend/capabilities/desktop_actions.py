"""Exact desktop Project actions, retaining all historical v1 definitions."""
import json
from uuid import uuid4
from jsonschema import Draft202012Validator
from backend.capability_v2.atomic_web_contracts import obj
from backend.capability_v2.contracts import ExposurePolicy, BusinessInvariantContract
from backend.capability_v2.provider_contracts import CapabilitySpec, CapabilityBusinessError
from backend.platform_sdk.identity import find_active_user_by_role, get_user_summaries
from ..application.outcomes import project_outcome_port
from ..infrastructure.repository import ProjectManagementRepository
from ..infrastructure import desktop_repository as db
from .provider import descriptor_for

ID={'type':'string','minLength':1,'maxLength':128}
TEXT={'type':'string','maxLength':4096}
NULL={'type':['string','null'],'maxLength':4096}
BOOL={'type':'boolean'}
REV={'type':'integer','minimum':1}
STATE={'enum':['pending','in_review','approved','rejected','withdrawn']}
def array(schema, maximum=500): return {'type':'array','items':schema,'maxItems':maximum}
def success(data): return obj({'success':{'const':True},'data':data},('success','data'))
CONTENT=obj({key:TEXT for key in ('item_type','item_gid','item_title','current_scope','target_scope','reason','description','body')})
OPINION=obj({key:TEXT for key in ('actor_gid','approver_gid','action','decision','comment','created_at','timestamp')})
ORDER=obj({**{key:NULL for key in ('gid','project_gid','team_gid','order_type','title','applicant_gid','reviewer_gid','source_ref','share_scope','created_at','updated_at')},'status':STATE,'revision':REV,'content':CONTENT,'opinions':array(OPINION,200)},('gid','status','revision','title','applicant_gid'))
RESULT=obj({'success':{'const':True},'order_gid':ID,'status':STATE,'revision':REV},('success','order_gid','status','revision'))
TRANSITION=obj({'order_gid':ID,'expected_revision':REV,'comment':{**TEXT,'maxLength':2000}},('order_gid','expected_revision'))
SCOPE=obj({'item_type':{'enum':['project','approval']},'item_gid':ID,'item_title':TEXT,'current_scope':{'enum':['local','project','team']},'target_scope':{'enum':['project','team','global']},'reason':TEXT},('item_type','item_gid','item_title','current_scope','target_scope'))
FOLLOW=obj({'item_type':{'enum':['project','approval','task','issue','knowledge_item','rule','bop','gbop']},'item_gid':ID,'item_title':TEXT,'notify_on':array({'enum':['any_change','status_change','comment_added','resolved','assigned_to_me','mentioned']},6)},('item_type','item_gid'))
SHARE=obj({key:NULL for key in ('gid','list_gid','shared_to','permission','shared_by','created_at','updated_at','shared_to_name','shared_to_avatar')})
LOG=obj({key:NULL for key in ('gid','item_type','item_gid','list_gid','changed_by','field_name','old_value','new_value','created_at','changed_by_name')})
CHANGE=obj({**{key:NULL for key in ('item_type','item_gid','list_gid')},'limit':{'type':'integer','minimum':1,'maximum':500},'offset':{'type':'integer','minimum':0}})

def order(row):
    value={key:(str(row[key]) if row[key] is not None else None) for key in ORDER['properties'] if key in row and key not in ('content','opinions','revision')}
    value['revision']=int(row.get('revision') or 1)
    for key,schema in (('content',CONTENT),):
        raw=row.get(key) or {}
        if isinstance(raw,str): raw=json.loads(raw)
        value[key]={name:str(raw[name] or '') for name in schema['properties'] if name in raw}
    raw=row.get('opinions') or []
    if isinstance(raw,str): raw=json.loads(raw)
    value['opinions']=[{key:str(item[key] or '') for key in OPINION['properties'] if key in item} for item in raw]
    return value

def search(payload,context):
    clauses=['COALESCE(o.team_gid,p.team_id)=%s'];params=[context.team_gid]
    if not set(context.active_roles)&{'super_admin','team_admin'}:
        clauses.append('(o.applicant_gid=%s OR o.reviewer_gid=%s)');params.extend([context.user_gid,context.user_gid])
    for key in ('status','project_gid'):
        if payload.get(key): clauses.append('o.'+key+'=%s');params.append(payload[key])
    rows=ProjectManagementRepository().fetch_all('SELECT o.* FROM workmanship_proj_approval_orders o LEFT JOIN workmanship_proj_projects p ON p.gid=o.project_gid WHERE '+' AND '.join(clauses)+' ORDER BY o.updated_at DESC LIMIT 500',tuple(params))
    return {'success':True,'data':[order(row) for row in rows]}

def get(payload,context):
    from ..data.connection import get_project_management_conn
    with get_project_management_conn() as conn,conn.cursor() as cursor:
        row=db.require_order(cursor,payload['order_gid'],context)
    return {'success':True,'data':order(row)}

def create(payload,context):
    with db.transaction('project.approval.order.create',payload,context) as (cursor,result,replayed):
        if not replayed:
            gid=str(uuid4())
            cursor.execute('INSERT INTO workmanship_proj_approval_orders (gid,title,order_type,project_gid,team_gid,applicant_gid,reviewer_gid,source_ref,content) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',(gid,payload['title'],payload.get('order_type','general'),payload.get('project_gid'),context.team_gid,context.user_gid,payload.get('reviewer_gid'),payload.get('source_ref'),json.dumps(payload.get('content',{}),ensure_ascii=False)))
            result.update(success=True,data={'gid':gid})
        return dict(result)

def scope_upgrade(payload,context):
    levels=['local','project','team','global']
    if levels.index(payload['target_scope'])<=levels.index(payload['current_scope']): db.error('invalid_input','Target visibility must be higher.')
    reviewer=find_active_user_by_role({'project':'project_admin','team':'team_admin','global':'super_admin'}[payload['target_scope']],context.team_gid)
    if not reviewer: db.error('resource_not_found','No active reviewer is assigned to the target visibility.')
    table,owner,tenant={'project':('workmanship_proj_projects','owner_gid','team_id'),'approval':('workmanship_proj_approval_orders','applicant_gid','team_gid')}[payload['item_type']]
    with db.transaction('project.approval.scope_upgrade.create',payload,context) as (cursor,result,replayed):
        if not replayed:
            cursor.execute(f'SELECT share_scope FROM {table} WHERE gid=%s AND {owner}=%s AND {tenant}=%s FOR UPDATE',(payload['item_gid'],context.user_gid,context.team_gid))
            row=cursor.fetchone()
            if not row: db.error('permission_denied','Only the target owner may request a visibility change.')
            if str(row.get('share_scope') or 'local')!=payload['current_scope']: db.error('version_conflict','The target visibility has changed.')
            gid=str(uuid4())
            cursor.execute('INSERT INTO workmanship_proj_approval_orders (gid,title,order_type,project_gid,team_gid,applicant_gid,reviewer_gid,content) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',(gid,f"范围提升申请：{payload['item_title']}（{payload['current_scope']} → {payload['target_scope']}）",'scope_upgrade',None,context.team_gid,context.user_gid,reviewer,json.dumps(payload,ensure_ascii=False)))
            result.update(success=True,data={'gid':gid,'reviewer_gid':reviewer})
        return dict(result)

def follow(payload,context):
    with db.transaction('project.follow.create',payload,context) as (cursor,result,replayed):
        if not replayed:
            gid=str(uuid4())
            cursor.execute('SELECT gid FROM workmanship_work_follows WHERE user_gid=%s AND item_type=%s AND item_gid=%s FOR UPDATE',(context.user_gid,payload['item_type'],payload['item_gid']))
            if cursor.fetchone(): db.error('already_exists','The item is already followed.')
            cursor.execute('INSERT INTO workmanship_work_follows (gid,user_gid,item_type,item_gid,item_title,notify_on) VALUES (%s,%s,%s,%s,%s,%s)',(gid,context.user_gid,payload['item_type'],payload['item_gid'],payload.get('item_title',''),json.dumps(payload.get('notify_on',['status_change','resolved']))))
            target={'project':('workmanship_proj_projects','owner_gid','team_id'),'approval':('workmanship_proj_approval_orders','applicant_gid','team_gid')}.get(payload['item_type'])
            if target:
                cursor.execute(f'SELECT {target[1]} AS owner_gid FROM {target[0]} WHERE gid=%s AND {target[2]}=%s',(payload['item_gid'],context.team_gid))
                owner=(cursor.fetchone() or {}).get('owner_gid')
                if owner and owner!=context.user_gid: db.notification(cursor,owner,'new_follower',payload['item_type'],payload['item_gid'],'有人关注了你的内容')
            result.update(success=True,data={'gid':gid})
        return dict(result)

def shares(payload,context):
    data=project_outcome_port.invoke('project.sharing.read',{'operation':'shares.list.list','arguments':payload},context)
    if len(data['shares'])>500: db.error('dataset_too_large','The list share result exceeds 500 entries.')
    summaries=get_user_summaries(row.get('shared_to') for row in data['shares'])
    return {'shares':[{**{key:str(row[key]) if row[key] is not None else None for key in SHARE['properties'] if key in row},'shared_to_name':summaries.get(str(row.get('shared_to')),{}).get('name'),'shared_to_avatar':summaries.get(str(row.get('shared_to')),{}).get('avatar_url')} for row in data['shares']]}

def changes(payload,context):
    rows=project_outcome_port.invoke('project.change_log.read',{'operation':'change_logs.search','arguments':payload},context)
    return {'logs':[{key:str(row[key]) if row[key] is not None else None for key in LOG['properties'] if key in row} for row in rows]}

ENTRY=obj({**{key:TEXT for key in ('gid','section','author','author_name','author_gid','ai_status')},'id':{'type':['integer','string']},'parent_id':{'type':['integer','string','null']},'content':{**TEXT,'maxLength':65536},'resolved':BOOL,'read_by_human':BOOL,'sort_order':{'type':'number'},'created_at':{'type':['number','string']}},('id','gid','content'))
def knowledge_comments(payload,context):
    from backend.platform_sdk.knowledge import require_readable_item
    require_readable_item(payload['item_gid'],context)
    return project_outcome_port.invoke('project.list.read',{'operation':'item_entries.get','arguments':{'item_type':'knowledge_item','item_gid':payload['item_gid']}},context)

DEFINITIONS=[
 ('project.approval.order.search',obj({'status':STATE,'project_gid':ID}),success(array(ORDER)),False,search),
 ('project.approval.order.get',obj({'order_gid':ID},('order_gid',)),success(ORDER),False,get),
 ('project.approval.order.create',obj({'title':ID,'order_type':{'enum':['general']},'project_gid':NULL,'reviewer_gid':NULL,'source_ref':NULL,'content':CONTENT},('title',)),success(obj({'gid':ID},('gid',))),True,create),
 *[(f'project.approval.order.{action}',TRANSITION,RESULT,True,(lambda p,c,_action=action:db.transition('project.approval.order.'+_action,_action,p,c))) for action in ('start','approve','withdraw')],
 ('project.approval.scope_upgrade.create',SCOPE,success(obj({'gid':ID,'reviewer_gid':ID},('gid','reviewer_gid'))),True,scope_upgrade),
 ('project.follow.create',FOLLOW,success(obj({'gid':ID},('gid',))),True,follow),
 ('project.share.list',obj({'list_gid':ID},('list_gid',)),obj({'shares':array(SHARE)},('shares',)),False,shares),
 ('project.change_log.search',CHANGE,obj({'logs':array(LOG)},('logs',)),False,changes),
 ('project.knowledge_comment.list',obj({'item_gid':ID},('item_gid',)),obj({'entries':array(ENTRY)},('entries',)),False,knowledge_comments),
]

def register_desktop_capabilities(registry):
    for capability_id,input_schema,output_schema,write,service in DEFINITIONS:
        def handler(payload,context,_service=service,_input=input_schema,_output=output_schema):
            if not Draft202012Validator(_input).is_valid(payload): db.error('invalid_input','The payload does not match this Project action.')
            result=_service(payload,context)
            if not Draft202012Validator(_output).is_valid(result): db.error('provider_error','The Project result violates its closed model.')
            return result
        effect=('Commit ' if write else 'Read ')+capability_id.removeprefix('project.').replace('.',' ')+' within the authenticated tenant and participant policy.'
        spec=CapabilitySpec(id=capability_id,version=1,owner='project_management',description=effect,use_when=effect,do_not_use_when='A different Project operation or domain effect is requested.',risk='write' if write else 'read',confirmation='user' if write else 'none',permissions=('project.manage_any',) if capability_id.endswith('.approve') else ('project.view',),idempotent=True,input_schema=input_schema,output_schema=output_schema,tags=('project_management','desktop','closed'))
        descriptor=descriptor_for(spec).model_copy(update={'business_effect':effect,'exposure':ExposurePolicy(web=True,api=True,plugin=False,agent=False,mcp=False),'delegation_policy':'none','business_acceptance_criteria':(effect,'Writes persist their exact result with the actor, tenant, action and idempotency key in the same transaction.','Approval decisions enforce the assigned participant, expected revision, durable audit and notification.'),'business_invariants':(BusinessInvariantContract(rule_id=capability_id+'.actor_bound',version=1,statement='Authenticated tenant and stored participation determine access.',applies_when='The desktop action executes.',enforcement_ref='plugins/project_management/project_management_backend/infrastructure/desktop_repository.py',error_code='permission_denied',test_refs=('backend/tests/test_desktop_round5_project.py',)),),'no_business_invariant_reason':None})
        registry.register(spec,handler,descriptor=descriptor)
