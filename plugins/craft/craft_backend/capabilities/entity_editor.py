"""Exact-binding editor for Craft-owned project entities; no legacy/table escape.

Uses the legacy BOP write ledger from 202608070001, not the modern repository
ledger. Public/common and cross-domain objects retain their owner read paths.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import math

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityOutput, CapabilitySpec, CapabilityExecutionBudget
from backend.capability_v2.provider_contracts import CapabilityContext
from backend.capability_v2.contracts import BusinessInvariantContract, DomainErrorContract, LifecycleStatus, ResourceSelector, CapabilityDescriptorV2, ExposurePolicy
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.platform_sdk.identity import get_active_identity_profile
from backend.platform_sdk.artifacts import require_artifact
from backend.platform_sdk.project_access import can_edit_project_bop, list_user_project_memberships
from ..data.connection import get_craft_conn
from .bop_writes import content_hash
from .member_pictures import artifact_picture_ref
from backend.domain_ports.resource_authorization import resource_authorizers

READ_ID = 'craft.bop.entity.edit_snapshot.get'
WRITE_ID = 'craft.bop.entity.detail.patch'
_META = ('gid','project_gid','version_no','owner_gid','created_at','updated_at','created_by','is_deleted','is_archived','deleted_at','archived_at')
_IDENTITY = frozenset((*_META, 'bop_version_gid','version_gid','snapshot_gid','source_type','source_ref_gid','status','tenant_gid','team_gid','updated_by','factory_equip_ref_gid','factory_tooling_ref_gid','factory_tool_ref_gid','factory_role_ref_gid'))
_NONNULL = frozenset({'title','name','part_no','unit','vpps_part','params','ext','meta','image_ref','content_ref','applicable_scope','attachments','height_mm','quantity','headcount','part_feed'})


@dataclass(frozen=True)
class EntityType:
    table: str
    editable: dict[str,str]
    readonly: tuple[str,...] = _META

    @property
    def columns(self): return tuple(dict.fromkeys((*self.readonly, *self.editable)))


def _fields(kind, names): return dict.fromkeys(names.split(), kind)


_LINE = {'title':'text','vpps':'text','ext':'json'}
_PROCESS = {**_fields('text','name process_code vpps vpps_desc vpps_part'), 'standard_time':'number', 'part_feed':'boolean','params':'json','ext':'json'}
_STEPS = {**_fields('text','title operation_code vpps vpps_desc vpps_part'), **_fields('number','station_height op_req_height vd_time total_time'), 'floor_height_need':'integer','part_feed':'boolean','params':'json','ext':'json', 'process_flow_pic':'json','process_chart_pic':'json'}
_RESOURCE = {'title':'text','spec':'text','quantity':'positive_integer','vpps':'text','ext':'json'}
_PBOM_TEXT = 'part_no title unit material vpps vpps_desc parent_vpps parent_vpps_name bom_row bom_row_label component_id component_type component_version_status purchase_status variable_formula torque torque_importance ownership_user home configuration parent_bom_row catia_occurrence_name catia_file_name catia_uuid default_matrix abs_matrix rel_matrix local_bbox ecn fna geo_main_part ref_main_vpps_desc ref_main_vpps main_part_consistency geo_evidence lr_side remark temp_vpps'
TYPES = {
    'bop_line':EntityType('workmanship_bop_bop_line', dict(_LINE)),
    'bop_station':EntityType('workmanship_bop_bop_station', dict(_LINE)),
    'bop_process':EntityType('workmanship_bop_bop_process',_PROCESS, tuple(k for k in _META if k != 'owner_gid') + ('bop_version_gid','source_type','source_ref_gid')),
    'bop_steps':EntityType('workmanship_bop_bop_steps',_STEPS, tuple(k for k in _META if k != 'owner_gid') + ('source_type','source_ref_gid')),
    'bop_operator':EntityType('workmanship_bop_bop_operator',{**_LINE,'operator_code':'text','headcount':'positive_integer'}),
    'project_equipment':EntityType('workmanship_bop_bop_equipments',dict(_RESOURCE), _META + ('factory_equip_ref_gid','status')),
    'project_tooling':EntityType('workmanship_bop_bop_fixtures',dict(_RESOURCE), _META + ('factory_tooling_ref_gid','status')),
    'project_tools':EntityType('workmanship_bop_bop_tools',dict(_RESOURCE), _META + ('factory_tool_ref_gid','status')),
    'project_roles':EntityType('workmanship_bop_project_roles',{'name':'text','role_type':'text','headcount':'positive_integer','vpps':'text','ext':'json'}, tuple(k for k in _META if k not in {'is_deleted','is_archived','deleted_at','archived_at'}) + ('factory_role_ref_gid',)),
    'floor_height':EntityType('workmanship_bop_bop_floor_height',{'title':'text','height_mm':'integer','measured_at':'datetime','notes':'text','station_ref_gid':'reference','vpps':'text'}, tuple(k for k in _META if k != 'version_no') + ('measured_by','status')),
    'control_plan':EntityType('workmanship_bop_bop_control_plan',{'title':'text','display_id':'text','content_ref':'json','applicable_scope':'json','attachments':'json','vpps':'text'},_META + ('status',)),
    'process_chart':EntityType('workmanship_bop_bop_process_charts',{'title':'text','display_id':'text','chart_type':'text','content_ref':'json','attachments':'json','vpps':'text'},_META + ('status',)),
    'jack_pos':EntityType('workmanship_bop_bop_jack_pos',{'title':'text','jack_pos_type':'text','ergonomic_score':'integer','posture_desc':'text','image_ref':'json','params':'json','vpps':'text'},_META + ('status',)),
    'pbom_part':EntityType('workmanship_bop_pbom',{**_fields('text',_PBOM_TEXT),'quantity':'positive_number','level':'integer','parent_gid':'reference','meta':'json'},('gid','snapshot_gid','vpps_source','vpps_reported_at','is_deleted','created_at','updated_at')),
}
ALIASES = {'asm_line_process':'bop_line','asm_station_process':'bop_station','asm_operator_process':'bop_operator','asm_operation':'bop_steps','usesPart':'pbom_part'}


def _error(code): raise CapabilityBusinessError(code, code)


def _type(value):
    kind = ALIASES.get(value,value)
    if kind not in TYPES: _error('unsupported_entity_type')
    return kind,TYPES[kind]


def _text(payload,key):
    value=payload.get(key)
    if not isinstance(value,str) or not value.strip() or len(value)>128: _error('invalid_input')
    return value.strip()


def _revision(payload,key):
    value=payload.get(key)
    if type(value) is not int or value<1: _error('invalid_input')
    return value


def _shape(payload,write):
    allowed={'version_gid','expected_revision','link_gid','expected_entity_token','idempotency_key','fields'} if write else {'version_gid','revision','link_gid','entity_type','entity_gid'}
    if not isinstance(payload,dict) or set(payload)-allowed: _error('invalid_input')
    _text(payload,'version_gid'); _revision(payload,'expected_revision' if write else 'revision')
    if write:
        for key in ('link_gid','expected_entity_token','idempotency_key'): _text(payload,key)
        if not isinstance(payload.get('fields'),dict) or not payload['fields'] or len(payload['fields'])>128: _error('invalid_input')
    elif 'link_gid' in payload:
        _text(payload,'link_gid')
        if 'entity_type' in payload or 'entity_gid' in payload: _error('invalid_input')
    else:
        _type(_text(payload,'entity_type')); _text(payload,'entity_gid')


def _identity(context):
    profile=get_active_identity_profile(context.user_gid)
    tenant=str(getattr(context,'team_gid',None) or '')
    actual=str((profile or {}).get('team_id') or f'user:{context.user_gid}')
    if not profile or str(profile.get('gid') or '') != context.user_gid or not tenant or tenant != actual: _error('permission_denied')


def _access(context,project,write):
    if not project: _error('permission_denied')
    # Empty roles forces Base to consult persisted responsibilities; no caller
    # super_admin claim or payload project grants authority.
    manager=bool(can_edit_project_bop(context.user_gid,project,None,()))
    if write and not manager: _error('permission_denied')
    if not write and not manager and not any(str(row.get('project_gid'))==project for row in list_user_project_memberships(context.user_gid)): _error('permission_denied')
    return manager


def _transport(value):
    if isinstance(value,(datetime,date)): return value.isoformat()
    if isinstance(value,Decimal): return float(value)
    if isinstance(value,dict): return {key:_transport(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)): return [_transport(item) for item in value]
    return value


def _json(value):
    if isinstance(value,str):
        try: return json.loads(value)
        except ValueError: _error('invalid_stored_data')
    return value


def _project(cur,kind,row,version,lock=False):
    project=str(version['project_gid'] or '')
    if kind=='pbom_part':
        if row.get('snapshot_gid') != version.get('pbom_version_gid'): _error('permission_denied')
        cur.execute('SELECT project_gid FROM workmanship_bop_pbom_versions WHERE gid=%s' + (' FOR UPDATE' if lock else ''),(row['snapshot_gid'],))
        snapshot=cur.fetchone()
        if not snapshot or str(snapshot.get('project_gid') or '') != project: _error('permission_denied')
    elif str(row.get('project_gid') or '') != project: _error('permission_denied')
    if kind=='bop_process' and str(row.get('bop_version_gid') or '') != str(version['gid']): _error('permission_denied')


def _entity_data(spec,row):
    data={key:_transport(row.get(key)) for key in spec.columns}
    for key,mode in spec.editable.items():
        if mode=='json' and data[key] is not None: data[key]=_json(data[key])
        elif mode=='boolean' and data[key] is not None: data[key]=bool(data[key])
    return data


def _target(cur,payload,version,write):
    link=None
    if 'link_gid' in payload:
        cur.execute('SELECT l.gid AS link_gid,l.entry_gid,l.version_gid,l.link_type,l.entity_gid,l.is_primary,l.snapshot_data,e.title AS entry_title '
                    'FROM workmanship_bop_bop_entry_links l JOIN workmanship_bop_bop_entries e ON e.gid=l.entry_gid AND e.version_gid=l.version_gid '
                    'WHERE l.version_gid=%s AND l.gid=%s AND l.is_deleted=0 AND l.deleted_at IS NULL AND e.is_deleted=0 AND e.deleted_at IS NULL'
                    + (' FOR UPDATE' if write else ''),(version['gid'],payload['link_gid']))
        link=cur.fetchone()
        if not link: _error('resource_not_found')
        link=dict(link); link['is_primary']=bool(link['is_primary'])
        kind,spec=_type(link['link_type']); gid=str(link['entity_gid'])
    else:
        kind,spec=_type(payload['entity_type']); gid=payload['entity_gid']
    frozen=bool(version.get('frozen_at'))
    if frozen:
        if not link or not link.get('snapshot_data'): _error('snapshot_unavailable')
        row=_json(link['snapshot_data'])
        if not isinstance(row,dict) or str(row.get('gid') or '') != gid: _error('invalid_stored_data')
    else:
        cur.execute(f"SELECT {','.join('`'+key+'`' for key in spec.columns)} FROM {spec.table} WHERE gid=%s" + (' FOR UPDATE' if write else ''),(gid,))
        row=cur.fetchone()
        if not row: _error('resource_not_found')
        row=dict(row)
    if row.get('is_deleted') or row.get('deleted_at') or row.get('is_archived') or row.get('archived_at'): _error('resource_not_found')
    _project(cur,kind,row,version,write)
    # A forged link cannot make a foreign project entity editable/readable.
    types=[kind,*[alias for alias,target in ALIASES.items() if target==kind]]
    cur.execute('SELECT 1 FROM workmanship_bop_bop_entry_links l JOIN workmanship_bop_bop_versions v ON v.gid=l.version_gid '
                f"WHERE l.entity_gid=%s AND l.link_type IN ({','.join(['%s']*len(types))}) AND l.is_deleted=0 AND l.deleted_at IS NULL "
                'AND v.is_deleted=0 AND (v.project_gid IS NULL OR v.project_gid<>%s) LIMIT 1',(gid,*types,version['project_gid']))
    if cur.fetchone(): _error('permission_denied')
    return kind,spec,gid,link,_entity_data(spec,row)


def _version(cur,gid,lock=False):
    cur.execute('SELECT gid,project_gid,revision,status,frozen_at,archived_at,pbom_version_gid FROM workmanship_bop_bop_versions '
                'WHERE gid=%s AND is_deleted=0' + (' FOR UPDATE' if lock else ''),(gid,))
    row=cur.fetchone()
    if not row: _error('resource_not_found')
    return dict(row)


def _assert_revision(version,expected):
    if version.get('revision') != expected: _error('revision_conflict')


def authorize_editor_version(version_gid,identity):
    """Fresh owner proof before Gateway can return a previously stored result.

    The ordinary BOP read authorizer intentionally accepts active members.
    Editor writes use this separate responsibility scope, never that read scope.
    """
    context=CapabilityContext(user_gid=identity.actor.user_id or '',team_gid=identity.tenant.tenant_id)
    try:
        _identity(context)
        with get_craft_conn() as conn,conn.cursor() as cur:
            version=_version(cur,version_gid)
        _access(context,str(version['project_gid'] or ''),True)
        return True
    except Exception:
        return False


def get_edit_snapshot(payload,context):
    _shape(payload,False); _identity(context)
    with get_craft_conn() as conn,conn.cursor() as cur:
        version=_version(cur,payload['version_gid']); _assert_revision(version,payload['revision'])
        manager=_access(context,str(version['project_gid'] or ''),False)
        kind,spec,gid,link,data=_target(cur,payload,version,False)
        _assert_revision(_version(cur,payload['version_gid']),payload['revision'])
    editable=bool(link and manager and not version.get('frozen_at') and not version.get('archived_at') and version.get('status') in {'draft','active'})
    reason='editable' if editable else 'unbound_target' if not link else 'frozen_version' if version.get('frozen_at') else 'read_only_version' if version.get('archived_at') or version.get('status') not in {'draft','active'} else 'manager_required'
    return CapabilityOutput(data={
        'version_gid':version['gid'],'revision':payload['revision'],
        'link':{key:_transport(link[key]) for key in ('link_gid','entry_gid','version_gid','link_type','entity_gid','is_primary')} if link else None,
        'target':{'type':kind,'gid':gid,'project_gid':version['project_gid'],'source':'frozen_snapshot' if version.get('frozen_at') else 'live'},
        'editability':{'can_edit':editable,'reason_code':reason},'entity_data':data,
        'editable_fields':list(spec.editable) if editable else [], 'readonly_fields':list(spec.readonly) if editable else list(spec.columns),
        'entity_token':content_hash(data),
    })


def _validate_json(value,context,depth=0):
    if depth>12: _error('invalid_input')
    if isinstance(value,str) and value.startswith('artifact:'):
        try:
            ref=artifact_picture_ref(value)
            require_artifact(ref.model_dump(mode='json'),context)
        except Exception: _error('invalid_reference')
        return
    if isinstance(value,dict):
        if len(value)>512: _error('invalid_input')
        if 'artifact_id' in value:
            try:
                from backend.capability_v2.contracts import ArtifactRef
                ref=ArtifactRef.model_validate(value)
                require_artifact(ref.model_dump(mode='json'),context)
            except Exception: _error('invalid_reference')
            return
        for key,item in value.items():
            if not isinstance(key,str): _error('invalid_input')
            if key in _IDENTITY or key.endswith('_gid'): _error('read_only_field')
            if key=='artifact_ref' and (not isinstance(item,dict) or 'artifact_id' not in item): _error('invalid_reference')
            _validate_json(item,context,depth+1)
    elif isinstance(value,list):
        if len(value)>512: _error('invalid_input')
        for item in value: _validate_json(item,context,depth+1)
    elif value is not None and not isinstance(value,(str,int,float,bool)): _error('invalid_input')
    elif isinstance(value,float) and not math.isfinite(value): _error('invalid_input')


def _changes(spec,fields,context):
    if set(fields)-set(spec.editable): _error('read_only_field')
    values={}
    for key,value in fields.items():
        mode=spec.editable[key]
        if key in _NONNULL and value is None: _error('invalid_input')
        if mode=='text':
            if value is not None and (not isinstance(value,str) or len(value)>2048): _error('invalid_input')
            if key in {'title','name'} and (not isinstance(value,str) or not value.strip()): _error('invalid_input')
        elif mode in {'number','integer','positive_integer','positive_number'}:
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value)): _error('invalid_input')
            if mode in {'integer','positive_integer'} and value is not None and type(value) is not int: _error('invalid_input')
            if mode.startswith('positive') and (value is None or value<=0): _error('invalid_input')
        elif mode=='boolean' and type(value) is not bool: _error('invalid_input')
        elif mode=='reference' and value is not None and (not isinstance(value,str) or not value or len(value)>128): _error('invalid_input')
        elif mode=='datetime' and value is not None:
            try:
                value=datetime.fromisoformat(value)
                if value.tzinfo is not None: _error('invalid_input')
            except (ValueError,TypeError): _error('invalid_input')
        elif mode=='json':
            if value is not None and not isinstance(value,(dict,list)): _error('invalid_input')
            _validate_json(value,context)
            if len(json.dumps(value,ensure_ascii=False).encode())>128*1024: _error('invalid_input')
        values[key]=value
    return values


def _references(cur,kind,fields,data,version):
    if kind=='floor_height' and fields.get('station_ref_gid'):
        cur.execute('SELECT gid,project_gid FROM workmanship_bop_bop_station WHERE gid=%s AND is_deleted=0 AND deleted_at IS NULL AND is_archived=0 FOR UPDATE',(fields['station_ref_gid'],))
        row=cur.fetchone()
        if not row or row['project_gid']!=version['project_gid']: _error('invalid_reference')
    if kind=='pbom_part' and fields.get('parent_gid'):
        seen={data['gid']}; gid=fields['parent_gid']
        for _ in range(128):
            if gid in seen: _error('invalid_reference')
            seen.add(gid)
            cur.execute('SELECT parent_gid FROM workmanship_bop_pbom WHERE gid=%s AND snapshot_gid=%s AND is_deleted=0 FOR UPDATE',(gid,data['snapshot_gid']))
            row=cur.fetchone()
            if not row: _error('invalid_reference')
            gid=row.get('parent_gid')
            if not gid: break
        else: _error('invalid_reference')


@contextmanager
def _transaction(conn):
    previous=conn.get_autocommit()
    try:
        conn.autocommit(False); conn.begin()
        yield
        conn.commit()
    except BaseException:
        conn.rollback(); raise
    finally:
        conn.autocommit(previous)


def patch_entity(payload,context):
    _shape(payload,True); _identity(context)
    fingerprint=content_hash(payload)
    ledger_key='entity-editor:'+content_hash({'capability':WRITE_ID+'@1','actor':context.user_gid,'tenant':context.team_gid,'version':payload['version_gid'],'key':payload['idempotency_key']})
    with get_craft_conn() as conn,_transaction(conn),conn.cursor() as cur:
        version=_version(cur,payload['version_gid'],True)
        _access(context,str(version['project_gid'] or ''),True)
        if version.get('frozen_at') or version.get('archived_at') or version.get('status') not in {'draft','active'}: _error('invalid_state')
        kind,spec,gid,link,data=_target(cur,payload,version,True)
        values=_changes(spec,payload['fields'],context)
        cur.execute('SELECT result_json,created_by,capability_id,version_gid FROM workmanship_craft_bop_write_idempotency WHERE idempotency_key=%s FOR UPDATE',(ledger_key,))
        prior=cur.fetchone()
        if prior:
            envelope=_json(prior['result_json'])
            if prior.get('created_by')!=context.user_gid or prior.get('capability_id')!=WRITE_ID+'@1' or prior.get('version_gid')!=version['gid'] or not isinstance(envelope,dict) or envelope.get('payload_hash')!=fingerprint or envelope.get('tenant_gid')!=context.team_gid or envelope.get('target')!={'type':kind,'gid':gid,'link_gid':link['link_gid']}: _error('idempotency_conflict')
            return CapabilityOutput(data=envelope['result'])
        _assert_revision(version,payload['expected_revision'])
        if content_hash(data)!=payload['expected_entity_token']: _error('entity_conflict')
        _references(cur,kind,{**data,**values},data,version)
        serialized=[json.dumps(value,ensure_ascii=False) if spec.editable[key]=='json' else value for key,value in values.items()]
        # Identifiers originate exclusively in the fixed owner map above.
        cur.execute(f"UPDATE {spec.table} SET {','.join('`'+key+'`=%s' for key in values)} WHERE gid=%s",(*serialized,gid))
        cur.execute('UPDATE workmanship_bop_bop_versions SET revision=revision+1,updated_at=NOW(6) WHERE gid=%s AND revision=%s AND is_deleted=0',(version['gid'],payload['expected_revision']))
        if cur.rowcount!=1: _error('revision_conflict')
        cur.execute(f"SELECT {','.join('`'+key+'`' for key in spec.columns)} FROM {spec.table} WHERE gid=%s",(gid,))
        stored=cur.fetchone()
        if not stored: _error('resource_not_found')
        after=_entity_data(spec,stored)
        result={'version_gid':version['gid'],'revision':payload['expected_revision']+1,'link_gid':link['link_gid'],'entity_type':kind,'entity_gid':gid,'changed_fields':list(values)}
        envelope={'payload_hash':fingerprint,'tenant_gid':context.team_gid,'target':{'type':kind,'gid':gid,'link_gid':link['link_gid']},'before_hash':content_hash(data),'after_hash':content_hash(after),'result':result}
        cur.execute('INSERT INTO workmanship_craft_bop_write_idempotency (idempotency_key,capability_id,version_gid,result_json,created_by) VALUES (%s,%s,%s,%s,%s)',(ledger_key,WRITE_ID+'@1',version['gid'],json.dumps(envelope,ensure_ascii=False),context.user_gid))
    return CapabilityOutput(data=result)


def _object(properties,required=()):
    return {'type':'object','properties':properties,'additionalProperties':False,'required':list(required)}


def register_entity_editor_capabilities(registry):
    resource_authorizers.register('craft-bop-editor-version',authorize_editor_version)
    text={'type':'string','minLength':1,'maxLength':128}; integer={'type':'integer','minimum':1}
    leaf={'description':'Provider-validated bounded entity value; identity keys are readonly and immutable ArtifactRefs require owner authorization.'}
    read_input=_object({'version_gid':text,'revision':integer,'link_gid':text,'entity_type':{'type':'string','enum':list(TYPES)+list(ALIASES)},'entity_gid':text},('version_gid','revision'))
    read_input['oneOf']=[{'required':['link_gid'],'not':{'anyOf':[{'required':['entity_type']},{'required':['entity_gid']}]}},{'required':['entity_type','entity_gid'],'not':{'required':['link_gid']}}]
    write_input=_object({'version_gid':text,'expected_revision':integer,'link_gid':text,'expected_entity_token':{'type':'string','pattern':'^[0-9a-f]{64}$'},'idempotency_key':text,'fields':_object({key:leaf for spec in TYPES.values() for key in spec.editable})},('version_gid','expected_revision','link_gid','expected_entity_token','idempotency_key','fields'))
    write_input['properties']['fields'].update(minProperties=1,maxProperties=128)
    string_list={'type':'array','maxItems':128,'items':{'type':'string'}}
    link=_object({key:({'type':'boolean'} if key=='is_primary' else text) for key in ('link_gid','entry_gid','version_gid','link_type','entity_gid','is_primary')},('link_gid','entry_gid','version_gid','link_type','entity_gid','is_primary'))
    read_output=_object({'version_gid':text,'revision':integer,'link':{'anyOf':[link,{'type':'null'}]},'target':_object({'type':{'type':'string','enum':list(TYPES)},'gid':text,'project_gid':text,'source':{'type':'string','enum':['live','frozen_snapshot']}},('type','gid','project_gid','source')),'editability':_object({'can_edit':{'type':'boolean'},'reason_code':{'type':'string'}},('can_edit','reason_code')),'entity_data':{'anyOf':[_object(dict.fromkeys(spec.columns,leaf),spec.columns) for spec in TYPES.values()]},'editable_fields':string_list,'readonly_fields':string_list,'entity_token':{'type':'string','pattern':'^[0-9a-f]{64}$'}},('version_gid','revision','link','target','editability','entity_data','editable_fields','readonly_fields','entity_token'))
    write_output=_object({'version_gid':text,'revision':integer,'link_gid':text,'entity_type':{'type':'string','enum':list(TYPES)},'entity_gid':text,'changed_fields':string_list},('version_gid','revision','link_gid','entity_type','entity_gid','changed_fields'))
    errors=tuple(DomainErrorContract(code=code,meaning=code.replace('_',' '),retryable=False) for code in ('invalid_input','permission_denied','resource_not_found','unsupported_entity_type','snapshot_unavailable','invalid_stored_data','read_only_field','revision_conflict','entity_conflict','invalid_reference','invalid_state','idempotency_conflict'))
    for capability,write,inputs,outputs,handler in ((READ_ID,False,read_input,read_output,get_edit_snapshot),(WRITE_ID,True,write_input,write_output,patch_entity)):
        effect='Commit declared business fields of one exact Craft project entity binding and its BOP revision in one durable transaction.' if write else 'Return the complete declared fields and authoritative editability of a Craft project entity at the selected BOP revision.'
        spec=CapabilitySpec(id=capability,version=1,owner='craft',description=effect,use_when='A Craft consumer opens or saves the editor for an exact BOP entity binding.',do_not_use_when='Common library standards, cross-domain objects, identity/source/lifecycle assignment or unbound mutation is required.',subject_concepts=('craft.bop.version','craft.bop.entry_link'),effects=((('write:' if write else 'read:')+'craft.bop.project_entity'),),risk='write' if write else 'read',permissions=('craft.write',) if write else ('craft.read',),plugin_callable=True,tags=('craft','experimental','entity_editor'),input_schema=inputs,output_schema=outputs,execution_budget=CapabilityExecutionBudget(max_input_bytes=256*1024,max_output_bytes=512*1024,collection_policy='bounded'))
        base=descriptor_from_provider_spec(spec).model_dump()
        base.update(lifecycle_status=LifecycleStatus.EXPERIMENTAL,exposure=ExposurePolicy(web=True,api=True,plugin=True,agent=False,mcp=False),exposure_policy_source='provider_explicit',authorization_policy='craft.entity_editor:fresh_base_project_scope',resource_selectors=(ResourceSelector(resource_type='craft-bop-version',payload_path='version_gid',required=True),),data_classification='confidential',delegation_policy='same_actor',business_effect=effect,business_acceptance_criteria=('The exact version, link and target remain in the authenticated project scope.','Only explicit owner fields are returned or changed; public and cross-domain entities retain their owner workflows.'),business_invariants=(BusinessInvariantContract(rule_id='craft.entity_editor.exact_project_binding',version=1,statement='Every entity belongs to the exact requested project/version binding and every mutation is authorized from fresh Base responsibilities.',applies_when='A project entity snapshot or patch is requested.',enforcement_ref=__name__+':_target',error_code='permission_denied',test_refs=('backend/tests/test_craft_entity_editor.py::test_foreign_project_refused','backend/tests/test_craft_entity_editor.py::test_revoked_manager_denied_even_replay_and_superadmin_claim')),),provider_ref=__name__,no_consumer_reason='Experimental owner contracts awaiting reviewed Demo consumer migration.',test_refs=({'path':'backend/tests/test_craft_entity_editor.py'},),domain_errors=errors,domain_errors_complete=True,consistency_policy='strong',operation_policy='required' if write else 'none',idempotency_policy='required' if write else 'none',replay_data_policy='projected' if write else 'metadata_only',concurrency_policy='expected_version' if write else 'none',expected_version_payload_path='expected_revision' if write else None,transaction_policy={'scope':'single Craft connection','ledger':'workmanship_craft_bop_write_idempotency','autocommit':'explicitly disabled and restored'} if write else {'scope':'revision checked before and after read'})
        # Craft commits its own entity/revision/ledger transaction. Base outcome
        # persistence is a separate participant, so do not claim Gateway-strong
        # cross-owner atomicity or attach a fake transactional-provider marker.
        if write:
            base['consistency_policy']='external'
            base['operation_policy']='optional'  # Synchronous editor outcome.
            base['resource_selectors']=(ResourceSelector(resource_type='craft-bop-editor-version',payload_path='version_gid',required=True),)
        registry.register(spec,handler,descriptor=CapabilityDescriptorV2.model_validate(base))
