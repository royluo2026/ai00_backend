"""Convert a proven stored BOP picture to an immutable ArtifactRef."""
from urllib.parse import quote
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.historical_artifacts import authorize_parent,records,select_record,resolve_stored,reference_hash,trusted_objects,issue_picture_grant
from ..data.connection import get_craft_conn
from ..routers._bop._constants import _BOP_PICS_DIR
from backend.core import storage,ois_storage

MAX_PICTURE_ENTRIES = 5000

def parent_attachments(kind,gid,context):
    if not context.user_gid:raise CapabilityBusinessError('permission_denied','An authenticated Craft reader is required.')
    with get_craft_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT gid,owner_gid,created_by,shared_team_gid,visibility,project_gid FROM workmanship_bop_bop_versions WHERE gid=%s',(gid,))
        parent=cursor.fetchone()
        if not parent:raise CapabilityBusinessError('resource_not_found','The BOP version is unavailable.')
        owner=str(parent.get('owner_gid') or parent.get('created_by') or '')
        authorize_parent(owner,parent.get('shared_team_gid'),parent.get('visibility'),parent.get('project_gid'),context)
        cursor.execute("SELECT process_flow_pic,process_chart_pic FROM workmanship_bop_bop_entries WHERE version_gid=%s AND is_deleted=FALSE AND ((process_flow_pic IS NOT NULL AND process_flow_pic NOT IN ('','[]','null')) OR (process_chart_pic IS NOT NULL AND process_chart_pic NOT IN ('','[]','null'))) LIMIT %s",(gid,MAX_PICTURE_ENTRIES+1))
        rows=cursor.fetchall()
    if len(rows)>MAX_PICTURE_ENTRIES:raise CapabilityBusinessError('dataset_too_large','Select a BOP version with at most 5000 picture entries.')
    attachments=[]
    for row in rows:
        for field in ('process_flow_pic','process_chart_pic'):
            values=records(row.get(field))
            if len(values)>15:raise CapabilityBusinessError('provider_error','Stored picture list exceeds its bound.')
            attachments.extend(values)
    return owner,attachments


def resolve_picture(payload,context):
    owner,values=parent_attachments('bop_version',payload['version_gid'],context)
    record=select_record(values,payload['reference_hash'])
    result=resolve_stored('craft','bop_version',payload['version_gid'],owner,record,context,static_root=_BOP_PICS_DIR.parent)
    if not result['artifact_ref']['media_type'].startswith('image/'):raise ValueError('image_required')
    return result


def list_picture_access(payload,context):
    owner,values=parent_attachments('bop_version',payload['version_gid'],context)
    unique={reference_hash(value):value for value in values}
    trusted,unavailable=trusted_objects(list(unique.values()),'craft','bop_version',payload['version_gid'],owner,context)
    ois_urls=ois_storage.generate_access_urls([record['object_key'] for record in trusted.values() if record['storage']=='ois'],600)
    minio_public=storage._get_minio_config().get('public_url','').rstrip('/')
    items=[]
    for digest,record in trusted.items():
        if not record['mime'].startswith('image/'):
            unavailable.append(digest);continue
        item={'reference_hash':digest,'access_grant':issue_picture_grant(record,payload['version_gid'],context),
            'media_type':record['mime'],'sha256':record['sha256'],'byte_size':record['byte_size']}
        if record['storage']=='ois' and ois_urls.get(record['object_key']):
            item['download_url']=ois_urls[record['object_key']]
        elif record['storage']=='minio' and minio_public:
            item['download_url']=minio_public+'/'+quote(record['object_key'],safe='/')
        items.append(item)
    return {'version_gid':payload['version_gid'],'items':items,'unavailable':list(dict.fromkeys(unavailable))}


def migration_parents(kind,actor_gid,after,limit):
    with get_craft_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT gid FROM workmanship_bop_bop_versions WHERE COALESCE(owner_gid,created_by)=%s AND gid>%s ORDER BY gid LIMIT %s',(actor_gid,after,limit))
        return cursor.fetchall()
