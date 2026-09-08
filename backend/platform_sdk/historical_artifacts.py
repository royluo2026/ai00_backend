"""Base-owned immutable attachment index. Only owner services supply stored records."""
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.contracts import ExposurePolicy
from backend.db.connection import get_conn
from backend.core import storage, ois_storage
from .artifacts import create_artifact, read_artifact
from .identity import get_user_summaries
from .business_images import image_type

MAXIMUM=5*1024*1024
UPLOADS=Path(__file__).resolve().parents[1]/'static'/'uploads'


def reference_hash(record):
    value={key:str(record.get(key) or '').strip() for key in ('object_key','storage','url')}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()).hexdigest()


def records(value):
    if isinstance(value,str):value=json.loads(value)
    if value is None:return []
    if not isinstance(value,list) or len(value)>200:raise ValueError('invalid_stored_attachment_list')
    return [{'url':row} if isinstance(row,str) else row for row in value if isinstance(row,(str,dict))]


def authorize_parent(owner_gid,tenant_gid,visibility,project_gid,context):
    owner=get_user_summaries([owner_gid]).get(str(owner_gid))
    tenant=tenant_gid or (owner or {}).get('team_id')
    if not owner or not tenant or tenant!=context.team_gid or owner.get('team_id')!=tenant:
        raise CapabilityBusinessError('resource_not_found','The attachment parent is unavailable in this tenant.')
    if context.user_gid==owner_gid:return
    if visibility in ('team','global'):return
    if visibility=='project' and project_gid:
        from .project_access import list_user_project_memberships
        if any(str(row.get('project_gid'))==str(project_gid) for row in list_user_project_memberships(context.user_gid)):return
    raise CapabilityBusinessError('permission_denied','The attachment parent is not visible to this reader.')


def _key(value):
    if not value or len(value)>2048 or unquote(value)!=value or '\\' in value or ':' in value or value.startswith('/') or any(part in ('','..','.') for part in value.split('/')):
        raise ValueError('invalid_stored_object_key')
    return value


def read_stored_attachment(record,*,static_root=UPLOADS):
    url=str(record.get('url') or '');key=str(record.get('object_key') or '')
    if record.get('storage')=='ois' and key:
        data=ois_storage.get_immutable(_key(key),maximum=MAXIMUM)
    elif url.startswith('/static/uploads/'):
        name=_key(url.removeprefix('/static/uploads/'))
        root=Path(static_root).resolve();candidate=root/name
        if candidate.is_symlink():raise ValueError('invalid_stored_attachment_path')
        target=candidate.resolve()
        if not target.is_relative_to(root) or any(parent.is_symlink() for parent in candidate.parents if parent!=root and parent.is_relative_to(root)):
            raise ValueError('invalid_stored_attachment_path')
        with target.open('rb') as stream:data=stream.read(MAXIMUM+1)
    else:
        configured=((storage._get_minio_config().get('public_url'),storage),(ois_storage._get_ois_config().get('public_base_url'),ois_storage))
        match=next(((base.rstrip('/')+'/',port) for base,port in configured if base and url.startswith(base.rstrip('/')+'/')),None)
        if match is None:raise ValueError('unsupported_stored_attachment_location')
        prefix,port=match;data=port.get_immutable(_key(url[len(prefix):]),maximum=MAXIMUM)
    if not isinstance(data,bytes) or len(data)>MAXIMUM:raise ValueError('stored_attachment_unavailable')
    extension=Path(str(record.get('name') or urlsplit(url).path or key)).suffix.lower()
    known={'.md':'text/markdown','.txt':'text/plain','.csv':'text/csv','.json':'application/json','.pdf':'application/pdf','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.xls':'application/vnd.ms-excel'}
    try:mime=image_type(data)
    except ValueError:
        mime=known.get(extension) or str(record.get('mime') or '')
        if mime in ('text/markdown','text/plain','text/csv','application/json'):
            value=data.decode('utf-8-sig')
            if '\x00' in value:raise ValueError('invalid_text_content')
            if mime=='application/json':json.loads(value)
        elif mime=='application/pdf':
            if not data.startswith(b'%PDF-'):raise ValueError('invalid_pdf_content')
        elif mime==known['.xlsx']:
            with ZipFile(io.BytesIO(data)) as archive:
                if '[Content_Types].xml' not in archive.namelist() or 'xl/workbook.xml' not in archive.namelist() or sum(item.file_size for item in archive.infolist())>32*1024*1024:raise ValueError('invalid_xlsx_content')
        elif mime==known['.xls']:
            if not data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):raise ValueError('invalid_xls_content')
        else:raise ValueError('unsupported_attachment_content')
    _verify(record,hashlib.sha256(data).hexdigest(),len(data),mime)
    return data,mime


def _verify(record,digest,size,mime):
    if record.get('sha256') and record['sha256']!=digest:raise ValueError('attachment_hash_mismatch')
    expected=record.get('byte_size',record.get('size'))
    if expected is not None and expected!=size:raise ValueError('attachment_size_mismatch')
    declared=record.get('mime') or record.get('media_type')
    if declared and declared!=mime:raise ValueError('attachment_mime_mismatch')


def resolve_stored(owner_domain,parent_type,parent_gid,owner_gid,record,context,*,static_root=UPLOADS):
    """Caller has just re-read/authorized the parent and proven record membership."""
    binding=hashlib.sha256(json.dumps([owner_domain,parent_type,parent_gid,context.team_gid,owner_gid,context.user_gid,reference_hash(record)],separators=(',',':')).encode()).hexdigest()
    name=str(record.get('name') or Path(urlsplit(str(record.get('url') or '')).path or str(record.get('object_key') or '')).name)
    if not name or len(name)>255 or '/' in name or '\\' in name:raise ValueError('invalid_attachment_name')
    with get_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT artifact_json FROM workmanship_base_legacy_artifact_bindings WHERE binding_hash=%s',(binding,))
        row=cursor.fetchone()
        if row:
            ref=json.loads(row['artifact_json'])
            _verify(record,ref['sha256'],ref['byte_size'],ref['media_type'])
            read_artifact(ref,context)
        else:
            data,mime=read_stored_attachment(record,static_root=static_root)
            ref=create_artifact(data,mime,context)
            cursor.execute('INSERT INTO workmanship_base_legacy_artifact_bindings (binding_hash,owner_domain,parent_type,parent_gid,tenant_gid,owner_gid,reader_gid,reference_hash,object_key,artifact_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE binding_hash=VALUES(binding_hash)',(binding,owner_domain,parent_type,parent_gid,context.team_gid,owner_gid,context.user_gid,reference_hash(record),str(record.get('object_key') or record.get('url') or ''),json.dumps(ref)))
            conn.commit()
            cursor.execute('SELECT artifact_json FROM workmanship_base_legacy_artifact_bindings WHERE binding_hash=%s',(binding,))
            ref=json.loads(cursor.fetchone()['artifact_json'])
            read_artifact(ref,context)
    return {'artifact_ref':ref,'name':name}


def select_record(values,digest):
    matches=[row for row in values if reference_hash(row)==digest]
    if not matches:raise CapabilityBusinessError('resource_not_found','The attachment is not attached to this parent.')
    if any(row!=matches[0] for row in matches):raise ValueError('ambiguous_attachment_reference')
    return matches[0]


def register_resolver(registry,capability_id,owner,handler,parent_types):
    from backend.base.desktop_artifacts import OUTPUT
    from backend.capability_v2.atomic_web_contracts import obj
    schema=obj({'parent_type':{'enum':list(parent_types)},'parent_gid':{'type':'string','minLength':1,'maxLength':128},'reference_hash':{'type':'string','pattern':'^[a-f0-9]{64}$'}},('parent_type','parent_gid','reference_hash'))
    effect='Resolve one historical attachment proven to belong to an authorized '+owner+' business parent into an immutable ArtifactRef.'
    spec=CapabilitySpec(id=capability_id,owner=owner,description=effect,use_when=effect,do_not_use_when='Only an object key, filesystem path or unowned attachment is supplied.',risk='read',permissions=('project.view',) if owner=='project_management' else ('knowledge.view',) if owner=='knowledge' else ('craft.read',),input_schema=schema,output_schema=OUTPUT)
    descriptor=descriptor_from_provider_spec(spec).model_copy(update={'business_effect':effect,'business_acceptance_criteria':('Parent, tenant and owner are re-read before resolving the stored attachment.','Repeated migration returns the same immutable reference and validates hash, size and MIME.'),'business_invariants':(),'no_business_invariant_reason':'This is an owner-authorized immutable attachment projection; domain ownership and Base content integrity enforce access.','exposure':ExposurePolicy(web=True,api=True,plugin=False,agent=False,mcp=False),'transaction_policy':{'mode':'provider','boundary':'owning_domain'},'evidence_policy':'optional'})
    registry.register(spec,handler,descriptor=descriptor)
