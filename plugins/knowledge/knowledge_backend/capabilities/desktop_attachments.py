"""Knowledge owns entry attachments and historical document file references."""
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.historical_artifacts import authorize_parent,records,select_record,resolve_stored,register_resolver
from ..infrastructure.repository import get_knowledge_conn

TABLES={'entry':'workmanship_know_entries','item':'workmanship_know_items'}


def parent_attachments(kind,gid,context):
    table=TABLES[kind]
    with get_knowledge_conn() as conn,conn.cursor() as cursor:
        cursor.execute(f'SELECT * FROM {table} WHERE gid=%s',(gid,));row=cursor.fetchone()
    if not row:raise CapabilityBusinessError('resource_not_found','The Knowledge attachment parent is unavailable.')
    owner=str(row.get('creator_gid') or '')
    authorize_parent(owner,row.get('team_gid') or row.get('team_id'),row.get('scope_type') or row.get('share_scope'),None,context)
    values=records(row.get('attachments')) if kind=='entry' else []
    if kind=='item' and row.get('file_path'):
        from pathlib import Path
        values=[{'url':row['file_path'],'name':Path(row['file_path']).name}]
    return owner,values


def resolve_attachment(payload,context):
    kind=payload['parent_type'];gid=payload['parent_gid']
    owner,values=parent_attachments(kind,gid,context)
    return resolve_stored('knowledge',kind,gid,owner,select_record(values,payload['reference_hash']),context)


def migration_parents(kind,actor_gid,after,limit):
    with get_knowledge_conn() as conn,conn.cursor() as cursor:
        cursor.execute(f'SELECT gid FROM {TABLES[kind]} WHERE creator_gid=%s AND gid>%s ORDER BY gid LIMIT %s',(actor_gid,after,limit))
        return cursor.fetchall()


def register_attachments(registry):
    register_resolver(registry,'knowledge.attachment.resolve','knowledge',resolve_attachment,('entry','item'))
