"""Deployment-only import of administrator-signed, independent upload provenance.

No API/Capability exposes this writer. The trusted Ed25519 public key comes only
from AI00_ATTACHMENT_BACKFILL_PUBLIC_KEY_PEM deployment configuration.
"""
import argparse
import base64
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from backend.db.connection import get_conn
from backend.platform_sdk.historical_artifacts import MAXIMUM,_key,object_hash
from backend.platform_sdk.identity import get_user_summaries

PARENTS={'project_management':('task','issue'),'knowledge':('entry','item'),'craft':('rule','bop_version')}
FIELDS=('storage_backend','object_key','tenant_gid','owner_gid','uploader_gid','sha256','byte_size','media_type','display_name','uploaded_at','parents','source_kind','source_ref')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def timestamp(value):
    parsed=datetime.fromisoformat(value)
    if not parsed.tzinfo:raise ValueError('timezone_required')
    return parsed


def import_manifest(document,*,apply=False):
    if set(document)!={'manifest','signature'}:raise ValueError('invalid_signed_manifest')
    manifest=document['manifest'];payload=canonical(manifest)
    if len(payload)>2*1024*1024:raise ValueError('manifest_too_large')
    key=serialization.load_pem_public_key(os.environ['AI00_ATTACHMENT_BACKFILL_PUBLIC_KEY_PEM'].encode())
    if not isinstance(key,Ed25519PublicKey):raise ValueError('trusted_ed25519_key_required')
    key.verify(base64.b64decode(document['signature'],validate=True),payload)
    if set(manifest)!={'schema_version','signer_gid','signed_at','objects'} or manifest['schema_version']!=1:raise ValueError('invalid_manifest_schema')
    signed_at=timestamp(manifest['signed_at']);objects=manifest['objects']
    if not isinstance(objects,list) or not 1<=len(objects)<=500:raise ValueError('bounded_objects_required')
    with get_conn() as conn,conn.cursor() as cursor:
        cursor.execute("SELECT gid FROM workmanship_auth_users WHERE gid=%s AND is_active=TRUE AND system_role='super_admin'",(manifest['signer_gid'],))
        if not cursor.fetchone():raise ValueError('active_administrator_required')
    ids=[value.get(field) for value in objects for field in ('owner_gid','uploader_gid')]
    identities=get_user_summaries(ids);prepared=[]
    for value in objects:
        if set(value)!=set(FIELDS):raise ValueError('invalid_upload_fields')
        for field in FIELDS:
            if field not in ('parents','byte_size') and (not isinstance(value[field],str) or not value[field] or len(value[field])>2048):raise ValueError('invalid_upload_field')
        if value['storage_backend'] not in ('ois','minio','local'):raise ValueError('invalid_storage_backend')
        _key(value['object_key'])
        if (type(value['byte_size']) is not int or not 0<=value['byte_size']<=MAXIMUM
            or len(value['sha256'])!=64 or any(c not in '0123456789abcdef' for c in value['sha256'])
            or len(value['display_name'])>255 or any(c in value['display_name'] for c in '/\\')
            or len(value['media_type'])>128 or timestamp(value['uploaded_at'])>signed_at):raise ValueError('invalid_upload_metadata')
        if value['source_kind'] not in ('upload_transaction','admin_migration_attestation'):raise ValueError('independent_provenance_required')
        for field in ('owner_gid','uploader_gid'):
            if identities.get(value[field],{}).get('team_id')!=value['tenant_gid']:raise ValueError('upload_identity_tenant_mismatch')
        parents=value['parents']
        if not isinstance(parents,list) or not 1<=len(parents)<=200:raise ValueError('bounded_parent_grants_required')
        for parent in parents:
            if (set(parent)!={'owner_domain','parent_type','parent_gid'} or parent['parent_type'] not in PARENTS.get(parent['owner_domain'],())
                or not isinstance(parent['parent_gid'],str) or not 1<=len(parent['parent_gid'])<=128):raise ValueError('invalid_parent_grant')
        row={field:value[field] for field in FIELDS if field not in ('parents','source_kind','source_ref')}
        row['object_hash']=object_hash(value['storage_backend'],value['object_key'])
        row['parents_json']=canonical(parents).decode()
        row['provenance_json']=canonical({'source_kind':value['source_kind'],'source_ref':value['source_ref'],'manifest_sha256':hashlib.sha256(payload).hexdigest(),'signer_gid':manifest['signer_gid'],'signed_at':manifest['signed_at'],'signature':document['signature'],'key_sha256':hashlib.sha256(key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).hexdigest()}).decode()
        prepared.append(row)
    if len({row['object_hash'] for row in prepared})!=len(prepared):raise ValueError('duplicate_object')
    inserted=0;existing=0;pending=[]
    with get_conn() as conn,conn.cursor() as cursor:
        for row in prepared:
            cursor.execute('SELECT * FROM workmanship_base_historical_uploads WHERE object_hash=%s',(row['object_hash'],));stored=cursor.fetchone()
            if stored:
                if any((json.loads(stored[field])!=json.loads(value) if field=='parents_json' else stored[field]!=value) for field,value in row.items() if field!='provenance_json'):raise ValueError('conflicting_upload_provenance')
                existing+=1;continue
            pending.append(row)
        if apply:
            for row in pending:
                columns=tuple(row)
                cursor.execute('INSERT INTO workmanship_base_historical_uploads ('+','.join(columns)+') VALUES ('+','.join(['%s']*len(columns))+')',tuple(row.values()))
                inserted+=1
        if apply:conn.commit()
    return {'objects':len(prepared),'inserted':inserted,'existing':existing,'applied':apply}


def unique_pairs(pairs):
    result={}
    for name,value in pairs:
        if name in result:raise ValueError('duplicate_json_key')
        result[name]=value
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();data=Path(args.manifest).read_bytes()
    if len(data)>3*1024*1024:raise ValueError('manifest_too_large')
    print(json.dumps(import_manifest(json.loads(data,object_pairs_hook=unique_pairs),apply=args.apply)))


if __name__=='__main__':main()
