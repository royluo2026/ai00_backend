"""Project-shared assembly preparation, independent of client downloads."""
import json
import base64
import zlib
from threading import Lock
from ..application.cache_preparation import prepare_cached_assembly,validate_preparation
from .cache_assembly_reader import read_assembly
from .cloud_model_cache_repository import CacheError,canonical

# One immutable shared batch, not per-user file readiness. Authorization and the
# DB generation/hash are checked before every hit; no local JT state is cached.
_recent=None
_recent_lock=Lock()

def encode_preparation(value):
    raw=canonical(value).encode('utf-8')
    if len(raw)>128*1024*1024:raise CacheError('cache_assembly_preparation_size_exceeded')
    # Large model metadata is highly repetitive (paths, matrices, XML). Keep the
    # exact immutable JSON/hash while staying below the database packet budget.
    encoded=canonical(dict(encoding='zlib-base64.v1',data=base64.b64encode(zlib.compress(raw)).decode('ascii')))
    return encoded

def decode_preparation(raw):
    value=json.loads(raw)
    if value.get('encoding')!='zlib-base64.v1':return value
    decoder=zlib.decompressobj()
    expanded=decoder.decompress(base64.b64decode(value['data'],validate=True),128*1024*1024+1)
    if len(expanded)>128*1024*1024 or not decoder.eof or decoder.unused_data:raise CacheError('cache_assembly_preparation_invalid')
    return json.loads(expanded)


def load_preparation(cache,binding,context):
    global _recent
    batch=cache._read(binding['batch_id'],context)
    if batch.get('preparation_status') not in ('ready','partial'):raise CacheError('cache_assembly_not_prepared')
    with cache.repo.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT preparation_json,preparation_hash FROM workmanship_sim_cache_assembly_preparations WHERE batch_id=%s',(binding['batch_id'],))
        row=cur.fetchone()
        if not row:raise CacheError('cache_assembly_not_prepared')
        key=(context.team_gid,binding['batch_id'],row['preparation_hash'])
        with _recent_lock:
            if _recent is not None and _recent[0]==key:
                if _recent[1]['identity']!=binding:raise CacheError('cache_snapshot_mismatch')
                return _recent[1]
        manifest=json.loads(row['preparation_json'])
        if manifest.get('encoding')!='chunks.v1':raise CacheError('cache_assembly_not_prepared')
        count=manifest.get('chunks')
        if type(count) is not int or not 1<=count<=512:raise CacheError('cache_assembly_preparation_invalid')
        cur.execute('SELECT chunk_index,chunk_text FROM workmanship_sim_cache_assembly_preparation_chunks WHERE batch_id=%s ORDER BY chunk_index',(binding['batch_id'],))
        pieces=cur.fetchall()
        if [p['chunk_index'] for p in pieces]!=list(range(count)):raise CacheError('cache_assembly_preparation_invalid')
    value=decode_preparation(''.join(p['chunk_text'] for p in pieces))
    if value['identity']!=binding or value['preparation_hash']!=row['preparation_hash']:raise CacheError('cache_snapshot_mismatch')
    validate_preparation(value)
    with _recent_lock:_recent=(key,value)
    return value


def prepare_batch(cache,batch_id,context):
    batch=cache._read(batch_id,context)
    if batch['status']!='completed' or batch.get('preparation_status')!='queued':return
    try:
        pinned=cache.repo.query_pinned(batch_id,context.team_gid,scope='roots',projection='structure',page_size=1)
        value=prepare_cached_assembly(read_assembly(cache,pinned['identity'],context),endpoint_id=batch['source_selector']['endpoint_id'])
        encoded=encode_preparation(value)
        with cache.repo.connect() as conn,conn.cursor() as cur:
            current=cache.repo._batch(cur,batch_id,context.team_gid,True)
            if current['preparation_status']!='queued':return
            cur.execute('DELETE FROM workmanship_sim_cache_assembly_preparation_chunks WHERE batch_id=%s',(batch_id,))
            cur.execute('DELETE FROM workmanship_sim_cache_assembly_preparations WHERE batch_id=%s',(batch_id,))
            chunks=[encoded[offset:offset+256*1024] for offset in range(0,len(encoded),256*1024)]
            cur.execute('INSERT INTO workmanship_sim_cache_assembly_preparations(batch_id,preparation_hash,preparation_json) VALUES(%s,%s,%s)',(batch_id,value['preparation_hash'],canonical(dict(encoding='chunks.v1',chunks=len(chunks)))))
            for index,chunk in enumerate(chunks):
                cur.execute('INSERT INTO workmanship_sim_cache_assembly_preparation_chunks(batch_id,chunk_index,chunk_text) VALUES(%s,%s,%s)',(batch_id,index,chunk))
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET preparation_status=%s,preparation_error=NULL,row_version=row_version+1 WHERE batch_id=%s',(value['status'],batch_id))
    except (ValueError,KeyError,TypeError) as exc:
        code=str(exc) if isinstance(exc,ValueError) else 'cache_assembly_preparation_invalid'
        with cache.repo.connect() as conn,conn.cursor() as cur:
            cur.execute('UPDATE workmanship_sim_cloud_cache_batches SET preparation_status=%s,preparation_error=%s,row_version=row_version+1 WHERE batch_id=%s',('failed',code[:255],batch_id))
