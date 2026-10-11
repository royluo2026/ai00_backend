"""All persisted BOP images are readable by active members, across teams."""
import json
from urllib.parse import unquote
from backend.capability_v2.contracts import ArtifactRef
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.artifacts import require_artifact, register_shared_download_authorizer
from backend.platform_sdk.identity import get_active_identity_profile
from backend.platform_sdk.historical_artifacts import records
from ..data.connection import get_craft_conn


def require_member(user_gid):
    profile = get_active_identity_profile(str(user_gid or ''))
    if not profile or profile['org_role'] not in ('member', 'super_admin'):
        raise CapabilityBusinessError('permission_denied', 'An active member is required to read BOP data.')
    return profile


def artifact_picture_ref(picture):
    url = picture.get('url', '') if isinstance(picture, dict) else picture
    if not isinstance(url, str) or not url.startswith('artifact:'):
        return None
    return ArtifactRef.model_validate(json.loads(unquote(url[9:].split('/', 1)[0])))


def picture_values(row):
    values = records(row.get('process_flow_pic')) + records(row.get('process_chart_pic'))
    meta = row.get('meta') or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    if isinstance(meta, dict):
        values += records(meta.get('cad_sim_pics'))
    return values


def authorize_shared_picture(record, identity):
    if record.artifact_ref.media_type not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
        return False
    profile = get_active_identity_profile(str(identity.actor.user_id or ''))
    if not profile or profile['org_role'] not in ('member', 'super_admin'):
        return False
    # The ID is only a bounded SQL candidate filter. Exact immutable-reference
    # matching below is mandatory; LIKE wildcards cannot grant access.
    pattern = '%artifact:%' + record.artifact_ref.artifact_id + '%'
    with get_craft_conn() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT e.process_flow_pic,e.process_chart_pic,e.meta FROM workmanship_bop_bop_entries e JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid WHERE e.is_deleted=FALSE AND (CAST(e.process_flow_pic AS CHAR) LIKE %s OR CAST(e.process_chart_pic AS CHAR) LIKE %s OR CAST(e.meta AS CHAR) LIKE %s) LIMIT 5001', (pattern,pattern,pattern))
        rows = cursor.fetchall()
    if len(rows) > 5000:
        return False
    for row in rows:
        try:
            values = picture_values(row)
        except (ValueError, TypeError):
            continue
        for picture in values:
            try:
                if artifact_picture_ref(picture) == record.artifact_ref:
                    return True
            except (ValueError, TypeError):
                continue
    return False


def validate_picture_updates(updates, context):
    """New private images require uploader access before BOP publication.

    Already persisted BOP images can be reused by any member. Other private
    attachments cannot become public merely by guessing their ArtifactRef.
    """
    for picture in picture_values(updates) + records(updates.get('cad_sim_pics')):
        ref = artifact_picture_ref(picture)
        if ref is not None:
            require_artifact(ref.model_dump(mode='json'), context)


def register_member_pictures():
    register_shared_download_authorizer('craft.bop.pictures', authorize_shared_picture)
