"""Closed export-template projection; the original read definition is immutable."""
from types import SimpleNamespace
from backend.capability_v2.atomic_web_contracts import obj
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from .export_templates import list_export_templates
from backend.platform_sdk.export_templates import create_export_template,update_export_template

TEXT={'type':'string','maxLength':4096}
COLUMN=obj({'key':TEXT,'label':TEXT,'width':{'type':'number','minimum':1,'maximum':1000},'include':{'type':'boolean'}},('key',))
STYLE=obj({**{key:TEXT for key in ('headerBg','headerFg','altRowBg','borderStyle')},'fontSize':{'type':'integer','minimum':6,'maximum':48}})
CONFIG=obj({'columns':{'type':'array','items':COLUMN,'maxItems':200},'styles':STYLE})
ITEM=obj({**{key:TEXT for key in ('gid','name','module','owner_gid','created_at','updated_at')},'is_shared':{'type':'boolean'},'config':CONFIG},('gid','name','module','owner_gid','created_at','updated_at','is_shared','config'))

def templates(payload,actor):
    result=list_export_templates(payload,SimpleNamespace(user_gid=actor['gid']))
    # Historical templates contain UI-only fields. Project only the supported editor model.
    for row in result['items']:
        old=row['config']
        if not isinstance(old,dict):raise CapabilityBusinessError('provider_error','Stored template configuration is invalid.')
        row['config']={}
        if 'columns' in old:row['config']['columns']=[{key:value for key,value in column.items() if key in COLUMN['properties']} for column in old['columns']]
        if 'styles' in old:row['config']['styles']={key:value for key,value in old['styles'].items() if key in STYLE['properties']}
    return result

DEFINITIONS=[('base.export_template.list',templates,obj({'module':{**TEXT,'maxLength':128},'limit':{'type':'integer','minimum':1,'maximum':500}}),obj({'items':{'type':'array','items':ITEM,'maxItems':500},'total':{'type':'integer','minimum':0,'maximum':500},'module':TEXT},('items','total','module')),False,'','Lists the authenticated user’s visible export templates with a bounded, closed editor configuration.')]

def create(payload,actor):
    gid=create_export_template(actor['gid'],payload['name'],payload['module'],payload['config'],payload.get('is_shared',False))
    return {'gid':gid}

def update(payload,actor):
    try:update_export_template(payload['gid'],actor['gid'],actor.get('org_role')=='super_admin',payload['changes'])
    except PermissionError as exc:raise CapabilityBusinessError('permission_denied','Only the template owner may edit it.') from exc
    except LookupError as exc:raise CapabilityBusinessError('resource_not_found','The template is unavailable.') from exc
    return {'gid':payload['gid']}

FIELDS={'name':{**TEXT,'minLength':1,'maxLength':128},'module':{**TEXT,'minLength':1,'maxLength':128},'config':CONFIG,'is_shared':{'type':'boolean'}}
RESULT=obj({'gid':{**TEXT,'minLength':1,'maxLength':128}},('gid',))
DEFINITIONS.extend([
 ('base.export_template.create',create,obj(FIELDS,('name','module','config')),RESULT,True,'','Creates one bounded export template with the authenticated user as its immutable owner.'),
 ('base.export_template.update',update,obj({'gid':RESULT['properties']['gid'],'changes':{**obj(FIELDS),'minProperties':1}},('gid','changes')),RESULT,True,'','Updates only the named fields of one stored template after proving owner or administrator authority.'),
])
