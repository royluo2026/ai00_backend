"""Durable project cache, independent of personal Simulation workspaces.

Every accepted page atomically persists rows, continuation work and its receipt.
The batch row serializes workers and controls. Connector plans have deterministic
IDs, so a crash between dispatch and saving the ID is safe to recover.
"""
from __future__ import annotations

from datetime import datetime, UTC
from contextlib import contextmanager
import hashlib
import json
import re
import uuid

from .connection import get_simulation_conn

SNAPSHOT_PAGE_SIZE = 500  # Existing @2 limit; Connector also caps actual page bytes.

class CacheError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def fields(value, prefix=''):
    result = {prefix: value} if prefix else {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(fields(child, prefix + '/' + str(key).replace('~', '~0').replace('/', '~1')))
    elif isinstance(value, list):
        for index, child in enumerate(value): result.update(fields(child, prefix + '/' + str(index)))
    return result


def _safe(value):
    """Fail closed if a future adapter leaks transport credentials into its bag."""
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(r'password|cookie|authorization|session_token|access_token|refresh_token|fms_ticket', key, re.I):
                raise CacheError('cache_sensitive_field_rejected')
            _safe(child)
    elif isinstance(value, list):
        for child in value: _safe(child)


def matches(value, filters, mode):
    bag = fields(value)
    checks = []
    for item in filters:
        key, op = item['field'], item['op']
        expected = json.loads(item.get('value_json', 'null'))
        actual = bag.get(key)
        if op == 'exists': matched = key in bag
        elif op == 'eq': matched = key in bag and type(actual) is type(expected) and actual == expected
        elif op == 'ne': matched = key in bag and not (type(actual) is type(expected) and actual == expected)
        elif op == 'contains': matched = key in bag and str(expected).casefold() in canonical(actual).casefold()
        elif op in ('empty','not_empty'): matched=key in bag and ((actual in (None,'',[],{})) == (op=='empty'))
        elif op in ('gt','gte','lt','lte'):
            comparable=key in bag and not isinstance(actual,bool) and not isinstance(expected,bool) and ((isinstance(actual,(int,float)) and isinstance(expected,(int,float))) or (isinstance(actual,str) and isinstance(expected,str)))
            matched=comparable and {'gt':lambda:actual>expected,'gte':lambda:actual>=expected,'lt':lambda:actual<expected,'lte':lambda:actual<=expected}[op]()
        else: raise CacheError('cache_filter_invalid')
        checks.append(matched)
    return (all(checks) if mode == 'and' else any(checks)) if checks else True


class CloudModelCacheRepository:
    def __init__(self, connection_factory=get_simulation_conn): self.connect = connection_factory

    def in_transaction(self,transaction):
        """Borrow the Gateway participant without committing repository calls.

        A rejected TC page rolls back to its own savepoint before the caller
        persists a failure state; the Gateway still owns the final commit.
        """
        @contextmanager
        def borrow():
            with transaction.cursor() as cur:cur.execute('SAVEPOINT cloud_model_cache_call')
            try:yield transaction
            except BaseException:
                with transaction.cursor() as cur:cur.execute('ROLLBACK TO SAVEPOINT cloud_model_cache_call')
                raise
            finally:
                with transaction.cursor() as cur:cur.execute('RELEASE SAVEPOINT cloud_model_cache_call')
        return CloudModelCacheRepository(borrow)

    @staticmethod
    def _batch(cur, batch_id, tenant_gid, lock=False):
        cur.execute('SELECT * FROM workmanship_sim_cloud_cache_batches WHERE batch_id=%s AND tenant_gid=%s' + (' FOR UPDATE' if lock else ''), (batch_id, tenant_gid))
        row = cur.fetchone()
        if not row: raise CacheError('cache_not_found')
        return row

    @staticmethod
    def public(row):
        return {key: row[key] for key in ('batch_id','project_gid','project_name','phase','display_name','source_hash','status','created_at','updated_at','completed_at','row_version','node_count','error_code','trigger_kind')} | {'source_selector':json.loads(row['selector_json']), 'preparation_status':row.get('preparation_status','not_prepared'), 'preparation_error':row.get('preparation_error')}

    def get(self, batch_id, tenant_gid):
        with self.connect() as conn, conn.cursor() as cur: return self.public(self._batch(cur,batch_id,tenant_gid))

    def resolve_visualization_node(self, batch_id, tenant_gid, node_key, *, authorize_project=None):
        """Resolve one published cache node without reading or rebuilding the tree."""
        with self.connect() as conn, conn.cursor() as cur:
            batch=self._batch(cur,batch_id,tenant_gid)
            if authorize_project is not None and not authorize_project(str(batch['project_gid'])):
                raise CacheError('cache_source_forbidden')
            if batch['status']!='completed':raise CacheError('cache_source_not_ready')
            cur.execute('SELECT data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND node_key=%s',
                (batch_id,node_key))
            row=cur.fetchone()
            if not row:raise CacheError('cache_source_node_not_found')
            try:
                data=json.loads(row['data_json']);structure=data['structure']
                if not isinstance(structure,dict):raise ValueError('structure_invalid')
                revision_uid=structure.get('item_revision_uid')
            except (KeyError,TypeError,ValueError):raise CacheError('cache_source_identity_missing')
            if structure.get('occurrence_id')!=node_key:raise CacheError('cache_source_stale')
            if not isinstance(revision_uid,str) or not revision_uid.strip():raise CacheError('cache_source_identity_missing')
            try:selector=json.loads(batch['selector_json'])
            except (TypeError,ValueError):raise CacheError('cache_source_stale')
            return {'batch_id':batch_id,'project_gid':str(batch['project_gid']),
                'source_selector':selector,'item_revision_uid':revision_uid}

    def list(self, tenant_gid, project_gids=None, limit=500, cursor=0):
        with self.connect() as conn, conn.cursor() as cur:
            if project_gids is not None and not project_gids: return []
            scope='' if project_gids is None else ' AND project_gid IN ('+','.join(['%s']*len(project_gids))+')'
            cur.execute('SELECT * FROM workmanship_sim_cloud_cache_batches WHERE tenant_gid=%s'+scope+' ORDER BY created_at DESC,batch_id DESC LIMIT %s OFFSET %s', (tenant_gid,*(sorted(project_gids) if project_gids is not None else []),limit,cursor))
            return [self.public(row) for row in cur.fetchall()]

    def candidates(self, limit=100):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT batch_id,tenant_gid,actor_gid FROM workmanship_sim_cloud_cache_batches WHERE status IN ('queued','running','waiting_connector') OR (status='completed' AND preparation_status='queued') ORDER BY updated_at LIMIT %s",(limit,))
            return cur.fetchall()

    @staticmethod
    def _task(cur, batch_id, kind, payload):
        key=digest({'kind':kind,'payload':payload})
        cur.execute('SELECT task_key FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND task_key=%s',(batch_id,key))
        if not cur.fetchone():
            cur.execute('INSERT INTO workmanship_sim_cloud_cache_tasks(batch_id,task_key,kind,payload_json,status,operation_id,attempt) VALUES(%s,%s,%s,%s,%s,%s,%s)',(batch_id,key,kind,canonical(payload),'queued',None,0))

    def create(self, *, tenant_gid, actor_gid, project_gid, project_name, phase, source_selector, request_key, trigger_kind='manual', display_name=None):
        if trigger_kind != 'manual': raise CacheError('cache_trigger_disabled')
        # Project name is a creation-time snapshot, not a stable retry identity.
        body=dict(project_gid=project_gid,phase=phase,source_selector=source_selector,trigger_kind=trigger_kind)
        request_hash=digest(body); now=datetime.now(UTC).isoformat(); bid=uuid.uuid4().hex
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT * FROM workmanship_sim_cloud_cache_batches WHERE tenant_gid=%s AND actor_gid=%s AND request_key=%s',(tenant_gid,actor_gid,request_key))
            prior=cur.fetchone()
            if prior:
                if prior['request_hash']!=request_hash: raise CacheError('cache_idempotency_conflict')
                return self.public(prior)
            # One counter lock serializes allocation across actors and requests.
            cur.execute('INSERT IGNORE INTO workmanship_sim_cloud_cache_versions(tenant_gid,project_gid,phase,next_version) VALUES(%s,%s,%s,0)',(tenant_gid,project_gid,phase))
            cur.execute('SELECT next_version FROM workmanship_sim_cloud_cache_versions WHERE tenant_gid=%s AND project_gid=%s AND phase=%s FOR UPDATE',(tenant_gid,project_gid,phase))
            version=cur.fetchone()['next_version']
            cur.execute('SELECT * FROM workmanship_sim_cloud_cache_batches WHERE tenant_gid=%s AND actor_gid=%s AND request_key=%s FOR UPDATE',(tenant_gid,actor_gid,request_key))
            prior=cur.fetchone()
            if prior:
                if prior['request_hash']!=request_hash: raise CacheError('cache_idempotency_conflict')
                return self.public(prior)
            if version==0:
                cur.execute('SELECT display_name FROM workmanship_sim_cloud_cache_batches WHERE tenant_gid=%s AND project_gid=%s AND phase=%s',(tenant_gid,project_gid,phase))
                existing=cur.fetchall()
                version=max([len(existing),*[int(match[1]) for row in existing if (match:=re.fullmatch(r'v([1-9][0-9]*)',row['display_name'],re.I))]])+1
            display_name='v'+str(version)
            cur.execute('UPDATE workmanship_sim_cloud_cache_versions SET next_version=%s WHERE tenant_gid=%s AND project_gid=%s AND phase=%s',(version+1,tenant_gid,project_gid,phase))
            cur.execute('INSERT INTO workmanship_sim_cloud_cache_batches(batch_id,tenant_gid,actor_gid,project_gid,project_name,phase,display_name,selector_json,source_hash,status,created_at,updated_at,completed_at,row_version,node_count,fields_json,error_code,trigger_kind,request_key,request_hash) VALUES('+','.join(['%s']*20)+')', (bid,tenant_gid,actor_gid,project_gid,project_name,phase,display_name,canonical(source_selector),'sha256:'+digest(source_selector),'queued',now,now,None,1,0,'[]',None,trigger_kind,request_key,request_hash))
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET preparation_status=%s WHERE batch_id=%s',('queued',bid))
            self._task(cur,bid,'children',dict(parent_path=[],cursor=0,page_size=200,refresh=False,generation=None))
            return self.public(self._batch(cur,bid,tenant_gid))

    def control(self,batch_id,tenant_gid,action,expected_version):
        with self.connect() as conn, conn.cursor() as cur:
            row=self._batch(cur,batch_id,tenant_gid,True)
            if row['row_version']!=expected_version: raise CacheError('cache_version_conflict')
            if action=='prepare':
                if row['status']!='completed':raise CacheError('cache_state_invalid')
                cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET preparation_status=%s,preparation_error=NULL,row_version=row_version+1 WHERE batch_id=%s',('queued',batch_id))
                return self.public(self._batch(cur,batch_id,tenant_gid))
            allowed={'pause':('queued','running','waiting_connector','waiting_auth'), 'resume':('paused','waiting_connector','waiting_auth','failed')}
            if action not in allowed or row['status'] not in allowed[action]: raise CacheError('cache_state_invalid')
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s,error_code=NULL,row_version=row_version+1,updated_at=%s WHERE batch_id=%s',('paused' if action=='pause' else 'queued',datetime.now(UTC).isoformat(),batch_id))
            return self.public(self._batch(cur,batch_id,tenant_gid))

    def next_task(self,batch_id,tenant_gid):
        with self.connect() as conn, conn.cursor() as cur:
            row=self._batch(cur,batch_id,tenant_gid)
            if row['status'] not in ('queued','running','waiting_connector'): return None
            cur.execute("SELECT * FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND status NOT IN ('completed','superseded') ORDER BY CASE kind WHEN 'snapshot' THEN 0 WHEN 'children' THEN 1 ELSE 2 END,task_key LIMIT 1",(batch_id,))
            task=cur.fetchone()
            if task: task['payload']=json.loads(task['payload_json'])
            return task

    def dispatch(self,batch_id,tenant_gid,queue,*,snapshot=False):
        """Serialize admission against pause/other workers; queue is deterministic."""
        with self.connect() as conn, conn.cursor() as cur:
            batch=self._batch(cur,batch_id,tenant_gid,True)
            if batch['status'] not in ('queued','running','waiting_connector'): return
            # Settle work already admitted to a runtime before upgrading. Pending
            # legacy tasks remain visible until the first valid snapshot receipt.
            cur.execute("SELECT * FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND status NOT IN ('completed','superseded') AND operation_id IS NOT NULL ORDER BY task_key LIMIT 1",(batch_id,))
            admitted=cur.fetchone()
            if admitted:
                admitted['payload']=json.loads(admitted['payload_json'])
                return admitted
            if snapshot:
                cur.execute("SELECT task_key FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND kind='snapshot' LIMIT 1",(batch_id,))
                if not cur.fetchone(): self._task(cur,batch_id,'snapshot',dict(cursor=0,page_size=SNAPSHOT_PAGE_SIZE,generation=None))
            cur.execute("SELECT * FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND status NOT IN ('completed','superseded') ORDER BY CASE kind WHEN 'snapshot' THEN 0 WHEN 'children' THEN 1 ELSE 2 END,task_key LIMIT 1",(batch_id,))
            task=cur.fetchone()
            if not task:
                self._validate_graph(conn,batch_id)
                now=datetime.now(UTC).isoformat()
                cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s,completed_at=%s,updated_at=%s,row_version=row_version+1 WHERE batch_id=%s',('completed',now,now,batch_id)); return
            task['payload']=json.loads(task['payload_json'])
            if task['operation_id']: return task
            operation=queue(batch,task)
            if isinstance(operation,dict):
                if batch['connector_device_id'] and batch['connector_device_id']!=operation['device_id']: raise CacheError('cache_device_changed')
                cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET connector_device_id=%s WHERE batch_id=%s',(operation['device_id'],batch_id))
                operation=operation['operation_id']
            cur.execute('UPDATE workmanship_sim_cloud_cache_tasks SET operation_id=%s,status=%s WHERE batch_id=%s AND task_key=%s',(operation,'running',batch_id,task['task_key']))
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s,error_code=NULL,updated_at=%s WHERE batch_id=%s',('running',datetime.now(UTC).isoformat(),batch_id))
            task['operation_id']=operation
            return task

    def failure(self,batch_id,tenant_gid,code,task=None):
        state='needs_refresh' if 'generation_stale' in code or 'path_invalid' in code or code in ('teamcenter_parent_path_not_found','cache_principal_changed','cache_device_changed') else 'waiting_auth' if 'login' in code or 'credential' in code or 'auth' in code or code=='teamcenter_session_expired' else 'waiting_connector' if code in ('connector_offline','runtime_v2_required','reconciliation_required','runtime_session_stale') else 'failed'
        with self.connect() as conn, conn.cursor() as cur:
            row=self._batch(cur,batch_id,tenant_gid,True)
            if row['status'] in ('paused','completed'): return
            if task:
                cur.execute('SELECT operation_id,attempt,status FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND task_key=%s',(batch_id,task['task_key']))
                current=cur.fetchone()
                if not current or current['status'] in ('completed','superseded') or current['operation_id']!=task.get('operation_id') or current['attempt']!=task['attempt']: return
                cur.execute('UPDATE workmanship_sim_cloud_cache_tasks SET operation_id=NULL,status=%s,attempt=attempt+1 WHERE batch_id=%s AND task_key=%s',('queued',batch_id,task['task_key']))
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET status=%s,error_code=%s,row_version=row_version+1,updated_at=%s WHERE batch_id=%s',(state,code[:255],datetime.now(UTC).isoformat(),batch_id))

    def apply_result(self,batch_id,tenant_gid,task,result,principal_hash=None):
        _safe(result)
        if len(canonical(result).encode())>8*1024*1024: raise CacheError('cache_page_too_large')
        receipt=task['task_key']; body_hash=digest(result)
        with self.connect() as conn, conn.cursor() as cur:
            batch=self._batch(cur,batch_id,tenant_gid,True)
            cur.execute('SELECT body_hash FROM workmanship_sim_cloud_cache_receipts WHERE batch_id=%s AND receipt_key=%s',(batch_id,receipt))
            prior=cur.fetchone()
            if prior:
                if prior['body_hash']!=body_hash: raise CacheError('cache_receipt_conflict')
                return False
            if batch['status'] in ('paused','needs_refresh','completed'): return False
            cur.execute('SELECT operation_id,attempt,status FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND task_key=%s',(batch_id,task['task_key']))
            current=cur.fetchone()
            if not current or current['status'] in ('completed','superseded') or current['operation_id']!=task.get('operation_id') or current['attempt']!=task['attempt']: return False
            if principal_hash:
                if not re.fullmatch('sha256:[a-f0-9]{64}',principal_hash) or (batch['principal_hash'] and batch['principal_hash']!=principal_hash): raise CacheError('cache_principal_changed')
                cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET principal_hash=%s WHERE batch_id=%s',(principal_hash,batch_id))
            if result.get('source_identity_hash')!=batch['source_hash']: raise CacheError('cache_source_mismatch')
            payload=task['payload']; catalog=set(json.loads(batch['fields_json'])); new_count=0
            if task['kind']=='children':
                generation=result.get('generation')
                if not isinstance(generation,str) or not re.fullmatch('[a-f0-9]{32}',generation) or (payload['generation'] and generation!=payload['generation']): raise CacheError('cache_generation_stale')
                if result.get('cursor')!=payload['cursor'] or result.get('complete') is not False or not isinstance(result.get('nodes'),list) or len(result['nodes'])>200: raise CacheError('cache_page_invalid')
                if result.get('parent',{}).get('occurrence_path')!=payload['parent_path']: raise CacheError('cache_page_invalid')
                next_cursor=result.get('next_cursor')
                count=result.get('child_count')
                if not isinstance(count,int) or count<0 or count>250000 or payload['cursor']+len(result['nodes'])>count or (next_cursor is None)!=(payload['cursor']+len(result['nodes'])==count) or (payload.get('expected_child_count') is not None and payload['expected_child_count']!=count): raise CacheError('cache_page_invalid')
                if next_cursor is not None and next_cursor!=payload['cursor']+len(result['nodes']): raise CacheError('cache_page_invalid')
                identities=set(); paths=set(); parent=result['parent']
                for node in result['nodes']:
                    path=node.get('occurrence_path'); key=node.get('occurrence_id')
                    if not isinstance(path,list) or len(path)!=len(payload['parent_path'])+1 or path[:-1]!=payload['parent_path'] or node.get('parent_occurrence_id')!=parent.get('occurrence_id') or key==parent.get('occurrence_id') or key in identities or canonical(path) in paths: raise CacheError('cache_page_invalid')
                    identities.add(key);paths.add(canonical(path))
                meta={key:value for key,value in result.items() if key not in ('nodes','parent')}
                for node in [result['parent'],*result['nodes']]:
                    key=node.get('occurrence_id'); path=node.get('occurrence_path')
                    if not key or not isinstance(path,list) or len(path)>128: raise CacheError('cache_page_invalid')
                    cur.execute('SELECT data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND node_key=%s',(batch_id,key))
                    old=cur.fetchone(); data=json.loads(old['data_json']) if old else {}
                    if old and node is not parent: raise CacheError('cache_page_invalid')
                    if old and node is parent: node={**node,'child_order':data['structure'].get('child_order',node.get('child_order',0))}
                    data.update(structure=node,page=meta); catalog.update(fields(data))
                    if len(canonical(data).encode())>8*1024*1024: raise CacheError('cache_page_too_large')
                    if old: cur.execute('UPDATE workmanship_sim_cloud_cache_nodes SET data_json=%s WHERE batch_id=%s AND node_key=%s',(canonical(data),batch_id,key))
                    else:
                        cur.execute('INSERT INTO workmanship_sim_cloud_cache_nodes(batch_id,node_key,data_json) VALUES(%s,%s,%s)',(batch_id,key,canonical(data))); new_count+=1
                    self._task(cur,batch_id,'properties',dict(node_key=key,occurrence_path=path))
                    if path!=payload['parent_path'] and node.get('has_children') is not False:
                        self._task(cur,batch_id,'children',dict(parent_path=path,cursor=0,page_size=200,refresh=False,generation=None))
                if next_cursor is not None:
                    if not result['nodes']: raise CacheError('cache_page_invalid')
                    self._task(cur,batch_id,'children',{**payload,'cursor':next_cursor,'generation':generation,'refresh':False,'expected_child_count':count})
            else:
                if not isinstance(result.get('properties'),dict): raise CacheError('cache_page_invalid')
                cur.execute('SELECT data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND node_key=%s',(batch_id,payload['node_key']))
                existing=cur.fetchone()
                if not existing: raise CacheError('cache_page_invalid')
                data=json.loads(existing['data_json']); data['properties_result']=result; catalog.update(fields(data))
                if len(canonical(data).encode())>8*1024*1024: raise CacheError('cache_page_too_large')
                cur.execute('UPDATE workmanship_sim_cloud_cache_nodes SET data_json=%s WHERE batch_id=%s AND node_key=%s',(canonical(data),batch_id,payload['node_key']))
            if batch['node_count']+new_count>250000: raise CacheError('cache_node_limit')
            if len(catalog)>10000 or any(len(path)>512 for path in catalog): raise CacheError('cache_field_limit')
            cur.execute('INSERT INTO workmanship_sim_cloud_cache_receipts(batch_id,receipt_key,body_hash) VALUES(%s,%s,%s)',(batch_id,receipt,body_hash))
            cur.execute('UPDATE workmanship_sim_cloud_cache_tasks SET status=%s WHERE batch_id=%s AND task_key=%s',('completed',batch_id,task['task_key']))
            cur.execute("SELECT task_key FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND status NOT IN ('completed','superseded') LIMIT 1",(batch_id,))
            complete=not cur.fetchone(); now=datetime.now(UTC).isoformat()
            if complete:
                self._validate_graph(conn,batch_id)
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET fields_json=%s,node_count=node_count+%s,status=%s,completed_at=%s,updated_at=%s,row_version=row_version+1 WHERE batch_id=%s',(canonical(sorted(catalog)),new_count,'completed' if complete else 'running',now if complete else None,now,batch_id))
            return True

    def apply_snapshot_result(self,batch_id,tenant_gid,task,result,principal_hash):
        """Commit complete occurrence rows, receipt and next page together.

        This uses the same cloud tables as v1. Local SQLite is never queried by
        consumers and an unfinished/local snapshot cannot mark a batch complete.
        """
        _safe(result)
        if len(canonical(result).encode())>8*1024*1024: raise CacheError('cache_page_too_large')
        body_hash=digest(result);payload=task['payload']
        with self.connect() as conn,conn.cursor() as cur:
            batch=self._batch(cur,batch_id,tenant_gid,True)
            cur.execute('SELECT body_hash FROM workmanship_sim_cloud_cache_receipts WHERE batch_id=%s AND receipt_key=%s',(batch_id,task['task_key']))
            prior=cur.fetchone()
            if prior:
                if prior['body_hash']!=body_hash: raise CacheError('cache_receipt_conflict')
                return False
            if batch['status'] not in ('queued','running','waiting_connector'): return False
            cur.execute('SELECT operation_id,attempt,status FROM workmanship_sim_cloud_cache_tasks WHERE batch_id=%s AND task_key=%s',(batch_id,task['task_key']))
            current=cur.fetchone()
            if task['kind']!='snapshot' or not current or current['status'] in ('completed','superseded') or current['operation_id']!=task.get('operation_id') or current['attempt']!=task['attempt']: return False
            if not isinstance(principal_hash,str) or not re.fullmatch('sha256:[a-f0-9]{64}',principal_hash) or (batch['principal_hash'] and batch['principal_hash']!=principal_hash): raise CacheError('cache_principal_changed')
            if result.get('source_identity_hash')!=batch['source_hash']: raise CacheError('cache_source_mismatch')
            generation=result.get('generation');structure_hash=result.get('structure_hash');count=result.get('node_count')
            if not isinstance(generation,str) or not re.fullmatch('[a-f0-9]{32}',generation) or (payload['generation'] and generation!=payload['generation']): raise CacheError('cache_generation_stale')
            if not isinstance(structure_hash,str) or not re.fullmatch('sha256:[a-f0-9]{64}',structure_hash) or (payload.get('structure_hash') and structure_hash!=payload['structure_hash']): raise CacheError('cache_generation_stale')
            if type(count)!=int or not 1<=count<=250000 or (payload.get('node_count') and count!=payload['node_count']): raise CacheError('cache_generation_stale')
            rows=result.get('rows');cursor=payload['cursor']
            if result.get('cursor')!=cursor or not isinstance(rows,list) or not 1<=len(rows)<=payload['page_size'] or cursor+len(rows)>count: raise CacheError('cache_page_invalid')
            complete=cursor+len(rows)==count;next_cursor=None if complete else cursor+len(rows)
            if result.get('next_cursor')!=next_cursor or result.get('complete') is not complete: raise CacheError('cache_page_invalid')
            lookup_keys=[]
            for data in rows:
                if not isinstance(data,dict) or not isinstance(data.get('structure'),dict) or not isinstance(data['structure'].get('occurrence_id'),str):raise CacheError('cache_page_invalid')
                lookup_keys.append(data['structure']['occurrence_id'])
            placeholders=','.join(['%s']*len(lookup_keys))
            cur.execute('SELECT node_key,data_json,snapshot_generation FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND node_key IN ('+placeholders+')',(batch_id,*lookup_keys))
            old_rows={row['node_key']:row for row in cur.fetchall()}
            catalog=set(json.loads(batch['fields_json']));new_count=0;keys=set();paths=set();inserts=[];updates=[]
            for offset,data in enumerate(rows):
                if not isinstance(data,dict) or set(data)!= {'structure','page','properties_result'}: raise CacheError('cache_page_invalid')
                node=data['structure'];meta=data['page'];props=data['properties_result']
                if not isinstance(node,dict) or not isinstance(meta,dict) or not isinstance(props,dict): raise CacheError('cache_page_invalid')
                key=node.get('occurrence_id');path=node.get('occurrence_path');child_count=meta.get('child_count')
                if not isinstance(key,str) or not 1<=len(key)<=128 or key in keys or not isinstance(path,list) or len(path)>128 or canonical(path) in paths: raise CacheError('cache_page_invalid')
                for edge in path:
                    if not isinstance(edge,dict) or set(edge)!= {'occurrence_uid','item_revision_uid'} or any(not isinstance(value,str) or not 1<=len(value)<=128 for value in edge.values()): raise CacheError('cache_page_invalid')
                if node.get('depth')!=len(path) or type(node.get('child_order'))!=int or node['child_order']<0 or type(child_count)!=int or not 0<=child_count<=count or node.get('has_children') is not (child_count>0): raise CacheError('cache_page_invalid')
                if (not path and (node.get('parent_occurrence_id') is not None or cursor!=0 or keys or node['child_order']!=0)) or (path and not isinstance(node.get('parent_occurrence_id'),str)): raise CacheError('cache_page_invalid')
                if props.get('source_identity_hash')!=batch['source_hash'] or not isinstance(props.get('properties'),dict) or not isinstance(props.get('raw_fields'),list) or len(props['raw_fields'])>64: raise CacheError('cache_page_invalid')
                for raw in props['raw_fields']:
                    if not isinstance(raw,dict) or raw.get('read_state') not in ('value','null','unavailable'): raise CacheError('cache_page_invalid')
                    try: json.loads(raw['value_json'])
                    except (KeyError,TypeError,ValueError) as exc: raise CacheError('cache_page_invalid') from exc
                keys.add(key);paths.add(canonical(path))
                old=old_rows.get(key)
                if old:
                    if old['snapshot_generation']==generation:raise CacheError('cache_page_invalid')
                    existing=json.loads(old['data_json'])['structure']
                    for attr in ('occurrence_path','parent_occurrence_id','child_order','item_revision_uid'):
                        if attr in existing and existing[attr]!=node.get(attr): raise CacheError('cache_generation_stale')
                    updates.append((canonical(data),generation,cursor+offset,batch_id,key))
                else:
                    inserts.append((batch_id,key,canonical(data),generation,cursor+offset));new_count+=1
                catalog.update(fields(data))
            if batch['node_count']+new_count>count: raise CacheError('cache_generation_stale')
            if len(catalog)>10000 or any(len(path)>512 for path in catalog): raise CacheError('cache_field_limit')
            if updates:cur.executemany('UPDATE workmanship_sim_cloud_cache_nodes SET data_json=%s,snapshot_generation=%s,snapshot_position=%s WHERE batch_id=%s AND node_key=%s',updates)
            if inserts:cur.executemany('INSERT INTO workmanship_sim_cloud_cache_nodes(batch_id,node_key,data_json,snapshot_generation,snapshot_position) VALUES(%s,%s,%s,%s,%s)',inserts)
            if complete:
                if batch['node_count']+new_count!=count: raise CacheError('cache_generation_stale')
                cur.execute('SELECT COUNT(*) AS count FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND snapshot_generation=%s',(batch_id,generation))
                if cur.fetchone()['count']!=count:raise CacheError('cache_generation_stale')
                self._validate_graph(conn,batch_id,require_order=True)
            else:
                self._task(cur,batch_id,'snapshot',dict(cursor=next_cursor,page_size=SNAPSHOT_PAGE_SIZE,generation=generation,structure_hash=structure_hash,node_count=count))
            cur.execute("UPDATE workmanship_sim_cloud_cache_tasks SET status='superseded' WHERE batch_id=%s AND kind!='snapshot' AND status='queued' AND operation_id IS NULL",(batch_id,))
            cur.execute('INSERT INTO workmanship_sim_cloud_cache_receipts(batch_id,receipt_key,body_hash) VALUES(%s,%s,%s)',(batch_id,task['task_key'],body_hash))
            cur.execute("UPDATE workmanship_sim_cloud_cache_tasks SET status='completed' WHERE batch_id=%s AND task_key=%s",(batch_id,task['task_key']))
            now=datetime.now(UTC).isoformat()
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET principal_hash=%s,fields_json=%s,node_count=node_count+%s,status=%s,completed_at=%s,updated_at=%s,row_version=row_version+1 WHERE batch_id=%s',(principal_hash,canonical(sorted(catalog)),new_count,'completed' if complete else 'running',now if complete else None,now,batch_id))
            if complete:
                from .cloud_model_cache_snapshot import completion_manifest
                final={**self.public(batch),'node_count':count,'status':'completed','completed_at':now,'updated_at':now,'row_version':batch['row_version']+1}
                manifest=completion_manifest(conn,final,generation,structure_hash,canonical)
                cur.execute('INSERT INTO workmanship_sim_cloud_cache_manifests(batch_id,manifest_json) VALUES(%s,%s)',(batch_id,canonical(manifest)))
            return True

    def query_pinned(self,batch_id,tenant_gid,**options):
        from .cloud_model_cache_snapshot import read
        return read(self,batch_id,tenant_gid,**options)

    @staticmethod
    def _validate_graph(conn,batch_id,require_order=False):
        """Stream large property bags; retain only topology until publication."""
        import pymysql.cursors
        graph={}; paths=set(); roots=[]; child_counts={}; child_orders={}
        with conn.cursor(pymysql.cursors.SSDictCursor) as stream:
            stream.execute('SELECT node_key,data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s',(batch_id,))
            while chunk:=stream.fetchmany(200):
                for row in chunk:
                    data=json.loads(row['data_json']); node=data['structure']
                    path=digest(node['occurrence_path']); parent=node.get('parent_occurrence_id')
                    if 'properties_result' not in data or path in paths: raise CacheError('cache_graph_invalid')
                    paths.add(path)
                    expected=0 if node.get('has_children') is False else data['page'].get('child_count')
                    graph[row['node_key']]=(parent,path,digest(node['occurrence_path'][:-1]),expected)
                    if parent is None: roots.append(path)
                    else:
                        child_counts[parent]=child_counts.get(parent,0)+1
                        if require_order:child_orders.setdefault(parent,[]).append(node['child_order'])
        if roots!=[digest([])]: raise CacheError('cache_graph_invalid')
        for key,(parent,path,parent_path,expected) in graph.items():
            if (parent is not None and (parent not in graph or parent_path!=graph[parent][1])) or child_counts.get(key,0)!=expected:
                raise CacheError('cache_graph_invalid')
            if require_order and sorted(child_orders.get(key,[]))!=list(range(expected)):raise CacheError('cache_graph_invalid')

    @staticmethod
    def _tree_order(conn,batch_id):
        """Read only topology; large property bags are fetched for the chosen page."""
        import pymysql.cursors
        children={};count=0
        with conn.cursor(pymysql.cursors.SSDictCursor) as stream:
            stream.execute("SELECT node_key,JSON_EXTRACT(data_json,'$.structure.parent_occurrence_id') AS parent_json,JSON_EXTRACT(data_json,'$.structure.child_order') AS child_order FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s",(batch_id,))
            while chunk:=stream.fetchmany(200):
                for row in chunk:
                    parent=row['parent_json']
                    if isinstance(parent,str):
                        try:parent=json.loads(parent)
                        except ValueError:pass  # SQLite returns an already decoded scalar.
                    children.setdefault(parent,[]).append((int(row['child_order'] or 0),row['node_key']));count+=1
        for siblings in children.values():siblings.sort()
        pending=[key for _,key in reversed(children.get(None,[]))];ordered=[];seen=set()
        while pending:
            key=pending.pop()
            if key in seen:raise CacheError('cache_graph_invalid')
            seen.add(key);ordered.append(key)
            pending.extend(child for _,child in reversed(children.get(key,[])))
        if len(ordered)!=count:raise CacheError('cache_graph_invalid')
        return ordered

    def query(self,batch_id,tenant_gid,*,search='',filters=(),mode='and',cursor=0,page_size=100):
        if mode not in ('and','or') or not 0<=cursor or not 1<=page_size<=500 or len(filters)>20: raise CacheError('cache_filter_invalid')
        with self.connect() as conn, conn.cursor() as cur:
            batch=self._batch(cur,batch_id,tenant_gid)
        with self.connect() as conn:
          import pymysql.cursors
          ordered=self._tree_order(conn,batch_id)
          if search or filters:
            matching=set()
            with conn.cursor(pymysql.cursors.SSDictCursor) as stream:
              stream.execute('SELECT node_key,data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s',(batch_id,))
              while chunk:=stream.fetchmany(1):
                for row in chunk:
                  if search.casefold() in row['data_json'].casefold() and matches(json.loads(row['data_json']),filters,mode):matching.add(row['node_key'])
            ordered=[key for key in ordered if key in matching]
          total=len(ordered);keys=ordered[cursor:cursor+page_size];rows=[];size=0
          with conn.cursor(pymysql.cursors.SSDictCursor) as cur:
            if keys:
              placeholders=','.join(['%s']*len(keys));ordering=' '.join('WHEN %s THEN '+str(index) for index in range(len(keys)))
              cur.execute('SELECT node_key,data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND node_key IN ('+placeholders+') ORDER BY CASE node_key '+ordering+' END',(batch_id,*keys,*keys))
            while keys and (chunk:=cur.fetchmany(1)):
                for row in chunk:
                    row_size=len(row['data_json'].encode())
                    if rows and size+row_size>4*1024*1024:keys=[];break
                    rows.append(row);size+=row_size
            return dict(batch=self.public(batch),rows=rows,total=total,fields=json.loads(batch['fields_json']),next_cursor=cursor+len(rows) if cursor+len(rows)<total else None)
