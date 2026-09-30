"""Fixed snapshot metadata and indexed reads, without live TC fallback."""
import base64
import hashlib
import json


def completion_manifest(conn,batch,generation,structure_hash,canonical):
    import pymysql.cursors
    digest=hashlib.sha256();count=0;unavailable=False;references_complete=True
    with conn.cursor(pymysql.cursors.SSDictCursor) as cur:
        cur.execute('SELECT node_key,snapshot_position,data_json FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s ORDER BY snapshot_position',(batch['batch_id'],))
        while rows:=cur.fetchmany(1):
            for row in rows:
                data=json.loads(row['data_json'])
                digest.update((canonical([row['snapshot_position'],row['node_key'],data])+'\n').encode('utf-8'));count+=1
                raw=data['properties_result']['raw_fields']
                unavailable|=any(field['read_state']=='unavailable' for field in raw)
                refs=next((field for field in raw if field['field']=='IMAN_Rendering'),None)
                references_complete&=refs is not None and refs['read_state']=='value'
    return metadata(batch,generation,structure_hash,'sha256:'+digest.hexdigest(),
                    {'structure':'complete','properties':'complete_with_unavailable' if unavailable else 'complete','geometry_references':'complete' if references_complete else 'partial','geometry_files':'not_requested'})


def metadata(batch,generation,structure_hash=None,snapshot_hash=None,readiness=None):
    return {**batch,'generation':generation,'schema_version':1,
            'configuration_date':batch['source_selector'].get('configuration_date'),
            'capture_started_at':None,'structure_hash':structure_hash,'snapshot_hash':snapshot_hash,
            'snapshot_hash_algorithm':'ai00.cache.snapshot.canonical-lines.v1' if snapshot_hash else None,
            'hash_status':'available' if snapshot_hash else 'unavailable',
            'readiness':readiness or {'structure':'complete','properties':'unverified','geometry_references':'unverified','geometry_files':'not_requested'},
            'spatial_semantics':{'status':'unverified','unit':None,'layout':None,'reference_frame':None,'direction':None}}


def read(repo,batch_id,tenant_gid,*,scope='roots',node_key=None,projection='structure',cursor=None,page_size=100,expected_generation=None,expected_snapshot_hash=None):
    from .cloud_model_cache_repository import CacheError,canonical,digest
    if scope not in ('roots','batch','children','node') or projection not in ('structure','properties','raw') or type(page_size)!=int or not 1<=page_size<=500 or (scope in ('children','node') and not node_key) or (scope in ('roots','batch') and node_key is not None):raise CacheError('cache_filter_invalid')
    with repo.connect() as conn,conn.cursor() as cur:
        batch=repo._batch(cur,batch_id,tenant_gid)
        if batch['status']!='completed':raise CacheError('cache_snapshot_not_ready')
        cur.execute('SELECT manifest_json FROM workmanship_sim_cloud_cache_manifests WHERE batch_id=%s',(batch_id,))
        stored=cur.fetchone()
        if stored:manifest=json.loads(stored['manifest_json'])
        else:
            cur.execute('SELECT snapshot_generation FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND snapshot_generation IS NOT NULL ORDER BY snapshot_generation,snapshot_position LIMIT 1',(batch_id,))
            first=cur.fetchone();manifest=metadata(repo.public(batch),first['snapshot_generation'] if first else None)
        identity={key:manifest[key] for key in ('batch_id','generation','snapshot_hash','schema_version')}
        if expected_generation is not None and expected_generation!=identity['generation']:raise CacheError('cache_generation_stale')
        if expected_snapshot_hash is not None:
            if identity['snapshot_hash'] is None:raise CacheError('cache_snapshot_hash_unavailable')
            if expected_snapshot_hash!=identity['snapshot_hash']:raise CacheError('cache_snapshot_mismatch')
        fingerprint=digest([batch_id,identity['generation'],scope,node_key,projection,expected_snapshot_hash])
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or not 1<=len(cursor)<=2048:raise ValueError()
                decoded=json.loads(base64.b64decode(cursor.encode('ascii'),altchars=b'-_',validate=True))
                if set(decoded)!= {'binding','order','key'} or decoded['binding']!=fingerprint or type(decoded['order'])!=int or decoded['order']<0 or not isinstance(decoded['key'],str) or not 1<=len(decoded['key'])<=128 or scope=='node':raise ValueError()
                after=decoded
            except (ValueError,TypeError,UnicodeError,KeyError) as exc:raise CacheError('cache_cursor_invalid') from exc
        if node_key is not None:
            cur.execute('SELECT node_key FROM workmanship_sim_cloud_cache_nodes WHERE batch_id=%s AND node_key=%s',(batch_id,node_key))
            if not cur.fetchone():raise CacheError('cache_node_not_found')
        where='batch_id=%s';params=[batch_id];order='snapshot_position' if scope=='batch' else 'sibling_order'
        if scope=='roots':where+=' AND parent_node_key IS NULL'
        elif scope=='children':where+=' AND parent_node_key=%s';params.append(node_key)
        elif scope=='node':where+=' AND node_key=%s';params.append(node_key)
        if after:
            where+=f' AND ({order}>%s OR ({order}=%s AND node_key>%s))';params.extend([after['order'],after['order'],after['key']])
        # Structure reads select only the small JSON subobject; raw properties stay in MySQL.
        selected="JSON_EXTRACT(data_json,'$.structure') AS structure_json" if projection=='structure' else 'data_json'
        import pymysql.cursors
        nodes=[];bytes_used=0;last=None;has_more=False
        with conn.cursor(pymysql.cursors.SSDictCursor) as stream:
            stream.execute(f'SELECT node_key,{order} AS page_order,{selected} FROM workmanship_sim_cloud_cache_nodes WHERE {where} ORDER BY {order},node_key LIMIT %s',(*params,page_size+1))
            while chunk:=stream.fetchmany(1):
                row=chunk[0]
                if len(nodes)==page_size:has_more=True;break
                data=json.loads(row['structure_json']) if projection=='structure' else json.loads(row['data_json'])
                node={'node_key':row['node_key'],**(data if projection=='structure' else data['structure'])}
                if projection!='structure':
                    node['properties_result']=data['properties_result']
                    field=next((f for f in data['properties_result']['raw_fields'] if f['field']=='IMAN_Rendering'),None)
                    node['geometry_refs']=json.loads(field['value_json']) if field and field['read_state']=='value' else None
                    if projection=='raw':node['raw_snapshot']=data
                length=len(canonical(node).encode('utf-8'))
                if length>18*1024*1024:raise CacheError('cache_page_too_large')
                if nodes and bytes_used+length>31*1024*1024:has_more=True;break
                nodes.append(node);bytes_used+=length;last=row
        next_cursor=None
        if has_more and last:
            if last['page_order'] is None:raise CacheError('cache_snapshot_unindexed')
            next_cursor=base64.urlsafe_b64encode(canonical({'binding':fingerprint,'order':last['page_order'],'key':last['node_key']}).encode()).decode()
        return {'identity':identity,'manifest':manifest if cursor is None and scope in ('roots','batch') else None,'nodes':nodes,'next_cursor':next_cursor}
