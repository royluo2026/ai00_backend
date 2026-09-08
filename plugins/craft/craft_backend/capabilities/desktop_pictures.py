"""Convert a proven stored BOP picture to an immutable ArtifactRef."""
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.historical_artifacts import authorize_parent,records,select_record,resolve_stored,reference_hash
from ..data.connection import get_craft_conn
from ..routers._bop._constants import _BOP_PICS_DIR

def parent_attachments(kind,gid,context):
    if not context.user_gid:raise CapabilityBusinessError('permission_denied','An authenticated Craft reader is required.')
    with get_craft_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT gid,owner_gid,created_by,shared_team_gid,visibility,project_gid FROM workmanship_bop_bop_versions WHERE gid=%s',(gid,))
        parent=cursor.fetchone()
        if not parent:raise CapabilityBusinessError('resource_not_found','The BOP version is unavailable.')
        owner=str(parent.get('owner_gid') or parent.get('created_by') or '')
        authorize_parent(owner,parent.get('shared_team_gid'),parent.get('visibility'),parent.get('project_gid'),context)
        cursor.execute('SELECT process_flow_pic,process_chart_pic FROM workmanship_bop_bop_entries WHERE version_gid=%s AND is_deleted=FALSE LIMIT 501',(gid,))
        rows=cursor.fetchall()
    if len(rows)>500:raise CapabilityBusinessError('dataset_too_large','Select a BOP version with at most 500 entries.')
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


def migration_parents(kind,actor_gid,after,limit):
    with get_craft_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT gid FROM workmanship_bop_bop_versions WHERE COALESCE(owner_gid,created_by)=%s AND gid>%s ORDER BY gid LIMIT %s',(actor_gid,after,limit))
        return cursor.fetchall()
