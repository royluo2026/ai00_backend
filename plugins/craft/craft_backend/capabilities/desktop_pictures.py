"""Convert a proven stored BOP picture to an immutable ArtifactRef."""
import hashlib,json
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.artifacts import create_artifact
from backend.platform_sdk.business_images import read_stored_image
from ..data.connection import get_craft_conn
from ..routers._bop._constants import _BOP_PICS_DIR

def reference_hash(record):
    value={key:str(record.get(key) or '').strip() for key in ('object_key','storage','url')}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()).hexdigest()

def resolve_picture(payload,context):
    if not context.user_gid:raise CapabilityBusinessError('permission_denied','An authenticated Craft reader is required.')
    with get_craft_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT gid FROM workmanship_bop_bop_versions WHERE gid=%s',(payload['version_gid'],))
        if not cursor.fetchone():raise CapabilityBusinessError('resource_not_found','The BOP version is unavailable.')
        cursor.execute('SELECT process_flow_pic,process_chart_pic FROM workmanship_bop_bop_entries WHERE version_gid=%s AND is_deleted=FALSE LIMIT 501',(payload['version_gid'],))
        rows=cursor.fetchall()
    if len(rows)>500:raise CapabilityBusinessError('dataset_too_large','Select a BOP version with at most 500 entries.')
    selected=None
    for row in rows:
        for field in ('process_flow_pic','process_chart_pic'):
            values=row.get(field) or []
            if isinstance(values,str):values=json.loads(values)
            if not isinstance(values,list) or len(values)>15:raise CapabilityBusinessError('provider_error','Stored picture list exceeds its bound.')
            for item in values:
                record={'url':item} if isinstance(item,str) else item
                if isinstance(record,dict) and reference_hash(record)==payload['reference_hash']:selected=record
    if selected is None:raise CapabilityBusinessError('resource_not_found','The picture is not attached to this BOP version.')
    try:data,mime=read_stored_image(selected,static_root=_BOP_PICS_DIR)
    except (ValueError,OSError) as exc:raise CapabilityBusinessError('artifact_unavailable','The attached picture cannot be read from the configured store.') from exc
    return {'artifact_ref':create_artifact(data,mime,context),'name':'bop-picture.'+mime.split('/')[1]}
