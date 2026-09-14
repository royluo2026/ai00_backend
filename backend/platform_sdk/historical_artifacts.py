"""Base-owned immutable attachment index. Only owner services supply stored records."""
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.contracts import ExposurePolicy
from backend.db.connection import get_conn
from backend.core import storage, ois_storage
from backend.config import get_settings
import jwt
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


def authorize_parent(owner_gid,tenant_gid,visibility,project_gid,context,*,allow_moved_owner=False):
    owner_gid=str(owner_gid or '')
    owner=get_user_summaries([owner_gid]).get(owner_gid)
    tenant=str(tenant_gid or (owner or {}).get('team_id') or '')
    reader_tenant=str(context.team_gid or '')
    # The parent's stored tenant remains authoritative after its owner moves teams.
    # The upload registry independently proves tenant, owner, and parent binding.
    moved_owner=(allow_moved_owner and owner_gid==str(context.user_gid or '')
                 and str((owner or {}).get('team_id') or '')==reader_tenant)
    if not owner or not tenant or (tenant!=reader_tenant and not moved_owner):
        raise CapabilityBusinessError('resource_not_found','The attachment parent is unavailable in this tenant.')
    if str(context.user_gid or '')==owner_gid:return
    if visibility in ('team','global'):return
    if visibility=='project' and project_gid:
        from .project_access import list_user_project_memberships
        if any(str(row.get('project_gid'))==str(project_gid) for row in list_user_project_memberships(context.user_gid)):return
    raise CapabilityBusinessError('permission_denied','The attachment parent is not visible to this reader.')


def _key(value):
    if not value or len(value)>2048 or unquote(value)!=value or '\\' in value or any(char in value for char in ':?#') or value.startswith('/') or any(part in ('','..','.') for part in value.split('/')):
        raise ValueError('invalid_stored_object_key')
    return value


def object_location(record,configured=None):
    """Normalize an untrusted locator for registry lookup, never as ownership proof."""
    url=str(record.get('url') or '');key=str(record.get('object_key') or '')
    if record.get('storage') in ('ois','minio','local') and key:
        return record['storage'],_key(key)
    if url.startswith('/static/uploads/'):
        return 'local',_key(url.removeprefix('/static/uploads/'))
    configured=configured or ((storage._get_minio_config().get('public_url'),'minio'),(ois_storage._get_ois_config().get('public_base_url'),'ois'))
    parsed=urlsplit(url)
    for base,backend in configured:
        if not base:continue
        parsed_base=urlsplit(base.rstrip('/'))
        prefix=parsed_base.path.rstrip('/')+'/'
        if (parsed.scheme,parsed.netloc)==(parsed_base.scheme,parsed_base.netloc) and parsed.path.startswith(prefix):
            return backend,_key(unquote(parsed.path[len(prefix):]))
    raise ValueError('unsupported_stored_attachment_location')


def object_hash(backend,key):
    return hashlib.sha256(json.dumps([backend,_key(key)],separators=(',',':')).encode()).hexdigest()


def trusted_object(record,owner_domain,parent_type,parent_gid,owner_gid,context,*,evidence_tenant_gid=None):
    backend,key=object_location(record)
    with get_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT * FROM workmanship_base_historical_uploads WHERE object_hash=%s',(object_hash(backend,key),))
        row=cursor.fetchone()
    parent={'owner_domain':owner_domain,'parent_type':parent_type,'parent_gid':parent_gid}
    if (not row or row['tenant_gid']!=(evidence_tenant_gid or context.team_gid) or row['owner_gid']!=owner_gid
        or row['storage_backend']!=backend or row['object_key']!=key
        or parent not in json.loads(row['parents_json']) or not row['provenance_json']):
        raise CapabilityBusinessError('object_ownership_unverified','Independent upload ownership evidence is required for this parent.')
    _verify(record,row['sha256'],row['byte_size'],row['media_type'])
    return {'storage':backend,'object_key':key,'name':row['display_name'],'mime':row['media_type'],'sha256':row['sha256'],'byte_size':row['byte_size']}


def trusted_objects(values,owner_domain,parent_type,parent_gid,owner_gid,context,*,evidence_tenant_gid=None):
    """Resolve a bounded parent attachment set with one registry query per chunk."""
    located=[];unavailable=[];configured=((storage._get_minio_config().get('public_url'),'minio'),(ois_storage._get_ois_config().get('public_base_url'),'ois'))
    for record in values:
        try:backend,key=object_location(record,configured)
        except ValueError:
            unavailable.append(reference_hash(record));continue
        located.append((record,backend,key,object_hash(backend,key)))
    rows={};unique=list(dict.fromkeys(item[3] for item in located))
    with get_conn() as conn,conn.cursor() as cursor:
        for offset in range(0,len(unique),50):
            chunk=unique[offset:offset+50]
            cursor.execute('SELECT * FROM workmanship_base_historical_uploads WHERE object_hash IN ('+','.join(['%s']*len(chunk))+')',tuple(chunk))
            rows.update((row['object_hash'],row) for row in cursor.fetchall())
    parent={'owner_domain':owner_domain,'parent_type':parent_type,'parent_gid':parent_gid}
    trusted={}
    for record,backend,key,digest in located:
        ref=reference_hash(record);row=rows.get(digest)
        if (not row or row['tenant_gid']!=(evidence_tenant_gid or context.team_gid) or row['owner_gid']!=owner_gid
            or row['storage_backend']!=backend or row['object_key']!=key
            or parent not in json.loads(row['parents_json']) or not row['provenance_json']):
            unavailable.append(ref);continue
        _verify(record,row['sha256'],row['byte_size'],row['media_type'])
        trusted[ref]={'storage':backend,'object_key':key,'name':row['display_name'],'mime':row['media_type'],'sha256':row['sha256'],'byte_size':row['byte_size']}
    return trusted,list(dict.fromkeys(unavailable))


def issue_picture_grant(record,parent_gid,context,ttl_seconds=600):
    now=int(time.time())
    return jwt.encode({'typ':'historical_picture','sub':str(context.user_gid),'tenant':str(context.team_gid),'parent_gid':str(parent_gid),
        'storage':record['storage'],'object_key':record['object_key'],'sha256':record['sha256'],'byte_size':record['byte_size'],
        'media_type':record['mime'],'iat':now,'exp':now+ttl_seconds},get_settings().jwt_secret,algorithm='HS256')


def redeem_picture_grant(grant,user_gid,tenant_gid):
    try:
        value=jwt.decode(grant,get_settings().jwt_secret,algorithms=['HS256'],options={'require':['typ','sub','tenant','parent_gid','storage','object_key','sha256','byte_size','media_type','iat','exp']})
    except jwt.PyJWTError as exc:
        raise CapabilityBusinessError('invalid_picture_grant','The picture access grant is invalid or expired.') from exc
    if value.get('typ')!='historical_picture' or value.get('sub')!=str(user_gid) or value.get('tenant')!=str(tenant_gid):
        raise CapabilityBusinessError('permission_denied','The picture access grant belongs to another reader.')
    record={'storage':value.get('storage'),'object_key':value.get('object_key'),'sha256':value.get('sha256'),'byte_size':value.get('byte_size'),'mime':value.get('media_type')}
    if (record['storage'] not in ('ois','minio','local') or not isinstance(record['byte_size'],int) or record['byte_size']<1 or record['byte_size']>MAXIMUM
        or not isinstance(record['sha256'],str) or len(record['sha256'])!=64 or not isinstance(record['mime'],str) or not record['mime'].startswith('image/')):
        raise CapabilityBusinessError('invalid_picture_grant','The picture access grant is malformed.')
    _key(str(record['object_key'] or ''))
    return record


def read_stored_attachment(record,*,static_root=UPLOADS):
    backend,key=object_location(record)
    url=str(record.get('url') or '')
    if backend=='ois':data=ois_storage.get_immutable(key,maximum=MAXIMUM)
    elif backend=='minio':data=storage.get_immutable(key,maximum=MAXIMUM)
    else:
        root=Path(static_root).resolve();candidate=root/key
        if candidate.is_symlink():raise ValueError('invalid_stored_attachment_path')
        target=candidate.resolve()
        if not target.is_relative_to(root) or any(parent.is_symlink() for parent in candidate.parents if parent!=root and parent.is_relative_to(root)):
            raise ValueError('invalid_stored_attachment_path')
        with target.open('rb') as stream:data=stream.read(MAXIMUM+1)
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


def resolve_stored(owner_domain,parent_type,parent_gid,owner_gid,record,context,*,static_root=UPLOADS,evidence_tenant_gid=None):
    """Caller has just re-read/authorized the parent and proven record membership."""
    trusted=trusted_object(record,owner_domain,parent_type,parent_gid,owner_gid,context,evidence_tenant_gid=evidence_tenant_gid)
    binding=hashlib.sha256(json.dumps([owner_domain,parent_type,parent_gid,context.team_gid,owner_gid,context.user_gid,reference_hash(record)],separators=(',',':')).encode()).hexdigest()
    name=str(record.get('name') or Path(urlsplit(str(record.get('url') or '')).path or str(record.get('object_key') or '')).name)
    if not name or len(name)>255 or '/' in name or '\\' in name:raise ValueError('invalid_attachment_name')
    with get_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT artifact_json FROM workmanship_base_legacy_artifact_bindings WHERE binding_hash=%s',(binding,))
        row=cursor.fetchone()
        if row:
            ref=json.loads(row['artifact_json'])
            _verify(trusted,ref['sha256'],ref['byte_size'],ref['media_type'])
            read_artifact(ref,context)
        else:
            data,mime=read_stored_attachment(trusted,static_root=static_root)
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
