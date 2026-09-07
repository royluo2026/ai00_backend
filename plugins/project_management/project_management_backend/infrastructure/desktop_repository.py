"""Tenant-bound desktop approval transactions with durable replay and notifications."""
from contextlib import contextmanager
import hashlib
import json
from uuid import uuid4
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from ..data.connection import get_project_management_conn


def error(code, message):
    raise CapabilityBusinessError(code, message)


@contextmanager
def transaction(capability_id, payload, context):
    key = str(getattr(context,'idempotency_key','') or '')
    if not key or len(key)>255: error('invalid_input','A bounded idempotency key is required.')
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    identity = (context.user_gid,context.team_gid,capability_id,key)
    with get_project_management_conn() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO workmanship_proj_desktop_operations (actor_gid,team_gid,capability_id,idempotency_key,payload_hash) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE actor_gid=VALUES(actor_gid)',(*identity,digest))
                cursor.execute('SELECT payload_hash,result_text FROM workmanship_proj_desktop_operations WHERE actor_gid=%s AND team_gid=%s AND capability_id=%s AND idempotency_key=%s FOR UPDATE',identity)
                prior = cursor.fetchone()
                if not prior or prior['payload_hash']!=digest: error('idempotency_conflict','This key belongs to a different request.')
                result = json.loads(prior['result_text']) if prior.get('result_text') else {}
                yield cursor,result,bool(prior.get('result_text'))
                cursor.execute('UPDATE workmanship_proj_desktop_operations SET result_text=%s,completed_at=CURRENT_TIMESTAMP(6) WHERE actor_gid=%s AND team_gid=%s AND capability_id=%s AND idempotency_key=%s',(json.dumps(result,ensure_ascii=False,separators=(',',':')),*identity))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def require_order(cursor, gid, context):
    cursor.execute('SELECT o.* FROM workmanship_proj_approval_orders o LEFT JOIN workmanship_proj_projects p ON p.gid=o.project_gid WHERE o.gid=%s AND COALESCE(o.team_gid,p.team_id)=%s FOR UPDATE',(gid,context.team_gid))
    row = cursor.fetchone()
    if not row: error('resource_not_found','The approval order is unavailable in this tenant.')
    if context.user_gid not in (str(row['applicant_gid']),str(row.get('reviewer_gid') or '')) and not set(context.active_roles)&{'super_admin','team_admin'}:
        error('permission_denied','The approval order belongs to another participant.')
    return dict(row)


def transition(capability_id, action, payload, context):
    with transaction(capability_id,payload,context) as (cursor,result,replayed):
        if replayed: return dict(result)
        row = require_order(cursor,payload['order_gid'],context)
        if int(row.get('revision') or 1)!=payload['expected_revision']: error('version_conflict','The order changed; reload before deciding.')
        expected = {'start':('pending',),'approve':('in_review',),'withdraw':('pending','in_review')}[action]
        required_actor = str(row.get('reviewer_gid') or '') if action=='approve' else str(row['applicant_gid'])
        if row['status'] not in expected: error('invalid_state','The current order state does not allow this transition.')
        if required_actor!=context.user_gid: error('permission_denied','Only the assigned participant may perform this transition.')
        target = {'start':'in_review','approve':'approved','withdraw':'withdrawn'}[action]
        if action=='approve' and row.get('order_type')=='scope_upgrade':
            content = row.get('content') or {}
            if isinstance(content,str): content=json.loads(content)
            table = {'project':'workmanship_proj_projects','approval':'workmanship_proj_approval_orders'}.get(content.get('item_type'))
            if not table: error('invalid_input','This request requires the target domain scope workflow.')
            cursor.execute(f'UPDATE {table} SET share_scope=%s WHERE gid=%s',(content['target_scope'],content['item_gid']))
            if cursor.rowcount!=1: error('resource_not_found','The scope-upgrade target is unavailable.')
        opinion = {'actor_gid':context.user_gid,'approver_gid':context.user_gid,'action':action,'decision':action,'comment':payload.get('comment','')}
        cursor.execute('UPDATE workmanship_proj_approval_orders SET status=%s,revision=revision+1,opinions=JSON_MERGE_PRESERVE(COALESCE(opinions,JSON_ARRAY()),%s),updated_at=NOW() WHERE gid=%s AND revision=%s',(target,json.dumps([opinion],ensure_ascii=False),payload['order_gid'],payload['expected_revision']))
        if cursor.rowcount!=1: error('version_conflict','The order changed concurrently.')
        cursor.execute('INSERT INTO workmanship_proj_approval_audit_events (gid,order_gid,actor_gid,team_gid,operation,idempotency_key,status,revision) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',(str(uuid4()),payload['order_gid'],context.user_gid,context.team_gid,action,context.idempotency_key,'succeeded',payload['expected_revision']+1))
        if action=='approve':
            notification(cursor,row['applicant_gid'],'scope_approved','approval',payload['order_gid'],'审批状态已更新')
        result.update(success=True,order_gid=payload['order_gid'],status=target,revision=payload['expected_revision']+1)
        return dict(result)


def notification(cursor, recipient, event, item_type, item_gid, title):
    cursor.execute('INSERT INTO workmanship_work_notifications (gid,user_gid,type,item_type,item_gid,title,body) VALUES (%s,%s,%s,%s,%s,%s,%s)',(str(uuid4()),recipient,event,item_type,item_gid,title,''))
