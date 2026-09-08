"""Project owns proof that a historical attachment belongs to a Task/Issue."""
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.historical_artifacts import authorize_parent,records,select_record,resolve_stored,register_resolver
from ..infrastructure.repository import ProjectManagementRepository


def parent_attachments(kind,gid,context):
    if kind not in ('task','issue'):raise ValueError('invalid_attachment_parent_type')
    repo=ProjectManagementRepository();row=repo.get_work_item(kind,gid)
    if not row or row.get('deleted_at') or row.get('is_deleted'):raise CapabilityBusinessError('resource_not_found','The attachment parent is unavailable.')
    project=repo.get_project(row['project_gid']) if row.get('project_gid') else None
    if row.get('project_gid') and not project:raise CapabilityBusinessError('resource_not_found','The attachment project is unavailable.')
    owner=str(row.get('owner_user_gid') or '')
    authorize_parent(owner,(project or {}).get('team_id'),row.get('share_scope'),row.get('project_gid'),context)
    return owner,records(row.get('attachments'))


def resolve_attachment(payload,context):
    kind=payload['parent_type'];gid=payload['parent_gid']
    owner,values=parent_attachments(kind,gid,context)
    return resolve_stored('project_management',kind,gid,owner,select_record(values,payload['reference_hash']),context)


def migration_parents(kind,actor_gid,after,limit):
    if kind not in ('task','issue'):raise ValueError('invalid_attachment_parent_type')
    return ProjectManagementRepository().fetch_all(f'SELECT gid FROM workmanship_proj_{kind}s WHERE owner_user_gid=%s AND gid>%s ORDER BY gid LIMIT %s',(actor_gid,after,limit))


def register_attachments(registry):
    register_resolver(registry,'project.attachment.resolve','project_management',resolve_attachment,('task','issue'))
