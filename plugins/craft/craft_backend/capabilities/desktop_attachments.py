"""Craft owns historical rule attachments."""
import json
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.historical_artifacts import authorize_parent,records,select_record,resolve_stored,register_resolver
from ..data.connection import get_craft_conn


def parent_attachments(kind,gid,context):
    if kind!='rule':raise ValueError('invalid_attachment_parent_type')
    with get_craft_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT owner_user_gid,creator_gid,applicable_scope,share_scope,attachments FROM workmanship_know_craft_rules WHERE gid=%s',(gid,));row=cursor.fetchone()
    if not row:raise CapabilityBusinessError('resource_not_found','The Craft attachment parent is unavailable.')
    scope=row.get('applicable_scope') or {}
    if isinstance(scope,str):scope=json.loads(scope)
    owner=str(row.get('owner_user_gid') or row.get('creator_gid') or '')
    authorize_parent(owner,scope.get('team_gid'),row.get('share_scope'),None,context)
    return owner,records(row.get('attachments'))


def resolve_attachment(payload,context):
    kind=payload['parent_type'];gid=payload['parent_gid'];owner,values=parent_attachments(kind,gid,context)
    return resolve_stored('craft',kind,gid,owner,select_record(values,payload['reference_hash']),context)


def migration_parents(kind,actor_gid,after,limit):
    with get_craft_conn() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT gid FROM workmanship_know_craft_rules WHERE COALESCE(owner_user_gid,creator_gid)=%s AND gid>%s ORDER BY gid LIMIT %s',(actor_gid,after,limit))
        return cursor.fetchall()


def register_attachments(registry):
    register_resolver(registry,'craft.attachment.resolve','craft',resolve_attachment,('rule',))
