from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import pytest

import json
import sqlite3
from contextlib import ExitStack
from backend.capability_v2.artifacts import ArtifactService,InMemoryArtifactStore,InMemoryObjectStorage
from backend.platform_sdk import artifacts


class LocalDatabase:
    """SQLite executes owner SQL; only the MySQL placeholder/upsert dialect differs."""
    def __init__(self):
        self.db=sqlite3.connect(':memory:',check_same_thread=False);self.db.row_factory=sqlite3.Row;self.cursor_value=None
        self.db.executescript('''
        CREATE TABLE workmanship_auth_users(gid TEXT PRIMARY KEY,name TEXT,avatar_url TEXT,team_id TEXT,is_active INTEGER,system_role TEXT DEFAULT 'member');
        INSERT INTO workmanship_auth_users VALUES('owner','Owner','','tenant',1,'member');
        INSERT INTO workmanship_auth_users VALUES('admin','Admin','','tenant',1,'super_admin');
        CREATE TABLE workmanship_base_historical_uploads(object_hash TEXT PRIMARY KEY,storage_backend TEXT,object_key TEXT,tenant_gid TEXT,owner_gid TEXT,uploader_gid TEXT,sha256 TEXT,byte_size INTEGER,media_type TEXT,display_name TEXT,uploaded_at TEXT,parents_json TEXT,provenance_json TEXT);
        CREATE TRIGGER historical_no_update BEFORE UPDATE ON workmanship_base_historical_uploads BEGIN SELECT RAISE(ABORT,'append-only'); END;
        CREATE TRIGGER historical_no_delete BEFORE DELETE ON workmanship_base_historical_uploads BEGIN SELECT RAISE(ABORT,'append-only'); END;
        CREATE TABLE workmanship_base_legacy_artifact_bindings(binding_hash TEXT PRIMARY KEY,owner_domain TEXT,parent_type TEXT,parent_gid TEXT,tenant_gid TEXT,owner_gid TEXT,reader_gid TEXT,reference_hash TEXT,object_key TEXT,artifact_json TEXT);
        CREATE TABLE workmanship_proj_tasks(gid TEXT PRIMARY KEY,owner_user_gid TEXT,project_gid TEXT,share_scope TEXT,attachments TEXT,deleted_at TEXT,is_deleted INTEGER);
        CREATE TABLE workmanship_proj_issues AS SELECT * FROM workmanship_proj_tasks;
        CREATE TABLE workmanship_proj_projects(gid TEXT PRIMARY KEY,team_id TEXT);
        CREATE TABLE workmanship_know_entries(gid TEXT PRIMARY KEY,creator_gid TEXT,team_id TEXT,share_scope TEXT,attachments TEXT);
        CREATE TABLE workmanship_know_items(gid TEXT PRIMARY KEY,creator_gid TEXT,team_gid TEXT,scope_type TEXT,file_path TEXT);
        CREATE TABLE workmanship_bop_bop_versions(gid TEXT PRIMARY KEY,owner_gid TEXT,created_by TEXT,shared_team_gid TEXT,visibility TEXT,project_gid TEXT);
        CREATE TABLE workmanship_bop_bop_entries(version_gid TEXT,process_flow_pic TEXT,process_chart_pic TEXT,is_deleted INTEGER);
        CREATE TABLE workmanship_know_craft_rules(gid TEXT PRIMARY KEY,owner_user_gid TEXT,creator_gid TEXT,applicable_scope TEXT,share_scope TEXT,attachments TEXT);
        ''')
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return self
    def commit(self):self.db.commit()
    def execute(self,sql,params=()):
        sql=sql.replace('%s','?').replace(' FOR UPDATE','').replace(' ON DUPLICATE KEY UPDATE binding_hash=VALUES(binding_hash)',' ON CONFLICT(binding_hash) DO NOTHING')
        self.cursor_value=self.db.execute(sql,params);return self.cursor_value.rowcount
    def fetchone(self):
        row=self.cursor_value.fetchone();row=dict(row) if row else None
        if row and 'parents_json' in row:row['parents_json']=json.dumps(json.loads(row['parents_json']),sort_keys=True) # MySQL JSON normalizes stored formatting.
        return row
    def fetchall(self):return [dict(row) for row in self.cursor_value.fetchall()]


def trust_fixture_upload(db,backend,key,content,mime,parents,*,owner='owner',tenant='tenant'):
    """Run the production signed importer, with only deployment key/identity SQL port fixtures."""
    import base64,os
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from backend.scripts.import_historical_upload_provenance import canonical,import_manifest
    db.db.execute('INSERT OR IGNORE INTO workmanship_auth_users VALUES(?,?,?,?,?,?)',(owner,'Fixture','',''+tenant,1,'member'))
    keypair=Ed25519PrivateKey.from_private_bytes(bytes(range(1,33)))
    public=keypair.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    manifest={'schema_version':1,'signer_gid':'admin','signed_at':'2026-09-08T00:00:00+00:00','objects':[{
        'storage_backend':backend,'object_key':key,'tenant_gid':tenant,'owner_gid':owner,'uploader_gid':owner,
        'sha256':hashlib.sha256(content).hexdigest(),'byte_size':len(content),'media_type':mime,'display_name':key.rsplit('/',1)[-1],
        'uploaded_at':'2026-09-01T00:00:00+00:00','parents':parents,'source_kind':'upload_transaction','source_ref':'fixture-original-upload-transaction'}]}
    document={'manifest':manifest,'signature':base64.b64encode(keypair.sign(canonical(manifest))).decode()}
    with patch.dict(os.environ,{'AI00_ATTACHMENT_BACKFILL_PUBLIC_KEY_PEM':public}),patch('backend.scripts.import_historical_upload_provenance.get_conn',return_value=db),patch('backend.platform_sdk.identity.get_conn',return_value=db):
        assert import_manifest(document,apply=False)=={'objects':1,'inserted':0,'existing':0,'applied':False}
        assert import_manifest(document,apply=True)=={'objects':1,'inserted':1,'existing':0,'applied':True}
        assert import_manifest(document,apply=True)=={'objects':1,'inserted':0,'existing':1,'applied':True}
    return document,public


def execute_historical_matrix(invoke=None):
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.platform_sdk.historical_artifacts import reference_hash
    from plugins.project_management.project_management_backend.capabilities.desktop_attachments import register_attachments as project
    from plugins.knowledge.knowledge_backend.capabilities.desktop_attachments import register_attachments as knowledge
    from plugins.craft.craft_backend.capabilities.desktop_exchange import register_desktop_exchange
    from plugins.craft.craft_backend.capabilities.desktop_attachments import register_attachments as craft
    from backend.scripts.migrate_historical_attachments import migrate
    registry=CapabilityRegistry();project(registry);knowledge(registry);craft(registry);register_desktop_exchange(registry)
    db=LocalDatabase();context=SimpleNamespace(user_gid='owner',team_gid='tenant',active_roles=('super_admin',))
    content=b'# historical document\n';picture=b'\x89PNG\r\n\x1a\nfixture'
    record={'url':'','storage':'ois','object_key':'owned/document.md','name':'document.md','mime':'text/markdown','sha256':hashlib.sha256(content).hexdigest(),'size':len(content)}
    photo={'url':'','storage':'ois','object_key':'owned/photo.png','name':'photo.png','mime':'image/png'}
    for kind in ('tasks','issues'):
        db.db.execute(f'INSERT INTO workmanship_proj_{kind} VALUES(?,?,?,?,?,?,?)',(kind+'-one','owner',None,'local',json.dumps([record]),None,0))
    db.db.execute('INSERT INTO workmanship_know_entries VALUES(?,?,?,?,?)',('entry-one','owner','tenant','local',json.dumps([record])))
    db.db.execute('INSERT INTO workmanship_know_items VALUES(?,?,?,?,?)',('item-one','owner','tenant','personal','https://fixture-store.invalid/owned/document.md'))
    db.db.execute('INSERT INTO workmanship_bop_bop_versions VALUES(?,?,?,?,?,?)',('bop-one','owner','owner','tenant','team',None))
    db.db.execute('INSERT INTO workmanship_bop_bop_entries VALUES(?,?,?,?)',('bop-one',json.dumps([photo]),'[]',0))
    db.db.execute('INSERT INTO workmanship_know_craft_rules VALUES(?,?,?,?,?,?)',('rule-one','owner','owner',json.dumps({'team_gid':'tenant'}),'team',json.dumps([record])))
    service=ArtifactService(InMemoryArtifactStore(),InMemoryObjectStorage());rows=[]
    with ExitStack() as stack:
        for target in ('backend.platform_sdk.historical_artifacts.get_conn','backend.platform_sdk.identity.get_conn','plugins.project_management.project_management_backend.infrastructure.repository.get_project_management_conn','plugins.knowledge.knowledge_backend.capabilities.desktop_attachments.get_knowledge_conn','plugins.craft.craft_backend.capabilities.desktop_pictures.get_craft_conn','plugins.craft.craft_backend.capabilities.desktop_attachments.get_craft_conn'):
            stack.enter_context(patch(target,return_value=db))
        stack.enter_context(patch.object(artifacts,'artifact_service',return_value=service))
        ois=stack.enter_context(patch('backend.core.ois_storage.get_immutable',side_effect=lambda key,**kwargs:picture if key.endswith('.png') else content))
        stack.enter_context(patch('backend.core.storage._get_minio_config',return_value={'public_url':'https://fixture-store.invalid'}))
        stack.enter_context(patch('backend.core.ois_storage._get_ois_config',return_value={}))
        stack.enter_context(patch('backend.core.storage.get_immutable',return_value=content))
        cases=[('project','task','tasks-one',record),('project','issue','issues-one',record),('knowledge','entry','entry-one',record),('knowledge','item','item-one',{'url':'https://fixture-store.invalid/owned/document.md'}),('craft','bop_version','bop-one',photo),('craft','rule','rule-one',record)]
        grant=lambda domain,kind,gid:{'owner_domain':domain,'parent_type':kind,'parent_gid':gid}
        trust_fixture_upload(db,'ois','owned/document.md',content,'text/markdown',[grant('project_management','task','tasks-one'),grant('project_management','issue','issues-one'),grant('knowledge','entry','entry-one'),grant('craft','rule','rule-one')])
        trust_fixture_upload(db,'minio','owned/document.md',content,'text/markdown',[grant('knowledge','item','item-one')])
        trust_fixture_upload(db,'ois','owned/photo.png',picture,'image/png',[grant('craft','bop_version','bop-one')])
        for owner,kind,gid,stored in cases:
            name='craft.bop.picture.resolve' if kind=='bop_version' else owner+'.attachment.resolve'
            payload={'version_gid':gid,'reference_hash':reference_hash(stored)} if kind=='bop_version' else {'parent_type':kind,'parent_gid':gid,'reference_hash':reference_hash(stored)}
            entry=registry.get(name,1);data=invoke(entry,payload,context) if invoke else entry.handler(payload,context)
            rows.append({'id':name,'version':1,'payload':payload,'provider_data':data,'input_schema':entry.descriptor.input_schema,'output_schema':entry.descriptor.output_schema})
            assert artifacts.read_artifact(data['artifact_ref'],context)==(picture if kind=='bop_version' else content)
            assert entry.handler(payload,context)==data
            replay=migrate(owner,kind,context,apply=True)
            assert replay['migrated']==1 and replay['rejected']==[]
            assert entry.handler(payload,context)==data
            with pytest.raises(Exception):entry.handler({**payload,'reference_hash':'0'*64},context)
            with pytest.raises(Exception):entry.handler(payload,SimpleNamespace(user_gid='owner',team_gid='other',active_roles=('super_admin',)))
        assert db.db.execute('SELECT COUNT(*) FROM workmanship_base_legacy_artifact_bindings').fetchone()[0]==6
        assert ois.call_count==5
        db.db.execute('DELETE FROM workmanship_proj_tasks')
        with pytest.raises(Exception):registry.get('project.attachment.resolve',1).handler({'parent_type':'task','parent_gid':'tasks-one','reference_hash':reference_hash(record)},context)
    return rows


def test_historical_attachment_reader_checks_content_and_fixed_paths(tmp_path):
    from backend.platform_sdk.historical_artifacts import read_stored_attachment
    content=b'# historical document\n';(tmp_path/'document.md').write_bytes(content)
    record={'url':'/static/uploads/document.md','name':'document.md','mime':'text/markdown','sha256':hashlib.sha256(content).hexdigest(),'size':len(content)}
    assert read_stored_attachment(record,static_root=tmp_path)==(content,'text/markdown')
    for changes in ({'size':1},{'sha256':'0'*64},{'mime':'image/png'},{'url':'/static/uploads/../secret.md'},{'url':'file:///secret.md'},{'url':'https://attacker.invalid/secret.md'},{'storage':'ois','object_key':'../secret'}):
        with patch('backend.core.storage._get_minio_config',return_value={}),patch('backend.core.ois_storage._get_ois_config',return_value={}):
            with pytest.raises(ValueError):read_stored_attachment({**record,**changes},static_root=tmp_path)


def test_historical_parent_rejects_cross_tenant_and_dangling_owner():
    from backend.platform_sdk.historical_artifacts import authorize_parent
    context=SimpleNamespace(user_gid='owner',team_gid='tenant',active_roles=())
    for identity in ({},{'owner':{'team_id':'other'}}):
        with patch('backend.platform_sdk.historical_artifacts.get_user_summaries',return_value=identity):
            with pytest.raises(Exception):authorize_parent('owner','tenant','local',None,context)


def test_owner_sql_migration_is_idempotent_and_gateway_bound():
    from backend.tests.support.desktop_gateway_matrix import DesktopGatewayMatrix
    assert len(execute_historical_matrix(DesktopGatewayMatrix()))==6


@pytest.mark.parametrize('backend',('minio','local'))
@pytest.mark.parametrize('proof',('missing','foreign_tenant','foreign_owner','wrong_parent'))
def test_owned_knowledge_item_cannot_launder_an_unregistered_foreign_object(backend,proof):
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from backend.platform_sdk.historical_artifacts import reference_hash
    from plugins.knowledge.knowledge_backend.capabilities.desktop_attachments import resolve_attachment
    db=LocalDatabase();context=SimpleNamespace(user_gid='owner',team_gid='tenant',active_roles=('super_admin',))
    url='https://fixture-store.invalid/foreign/private.md' if backend=='minio' else '/static/uploads/foreign/private.md'
    if proof!='missing':
        trust_fixture_upload(db,backend,'foreign/private.md',b'private foreign tenant content','text/markdown',[{'owner_domain':'knowledge','parent_type':'item','parent_gid':'other-item' if proof=='wrong_parent' else 'forged-item'}],owner='other' if proof in ('foreign_tenant','foreign_owner') else 'owner',tenant='foreign-tenant' if proof=='foreign_tenant' else 'tenant')
    db.db.execute('INSERT INTO workmanship_know_items VALUES(?,?,?,?,?)',('forged-item','owner','tenant','personal',url))
    service=ArtifactService(InMemoryArtifactStore(),InMemoryObjectStorage())
    with ExitStack() as stack:
        for target in ('backend.platform_sdk.historical_artifacts.get_conn','backend.platform_sdk.identity.get_conn','plugins.knowledge.knowledge_backend.capabilities.desktop_attachments.get_knowledge_conn'):
            stack.enter_context(patch(target,return_value=db))
        stack.enter_context(patch.object(artifacts,'artifact_service',return_value=service))
        stack.enter_context(patch('backend.core.storage._get_minio_config',return_value={'public_url':'https://fixture-store.invalid'}))
        stack.enter_context(patch('backend.core.ois_storage._get_ois_config',return_value={}))
        read=stack.enter_context(patch('backend.core.storage.get_immutable',return_value=b'private foreign tenant content'))
        with pytest.raises(CapabilityBusinessError) as rejected:
            resolve_attachment({'parent_type':'item','parent_gid':'forged-item','reference_hash':reference_hash({'url':url})},context)
        assert rejected.value.code=='object_ownership_unverified'
        read.assert_not_called()
        assert db.db.execute('SELECT COUNT(*) FROM workmanship_base_legacy_artifact_bindings').fetchone()[0]==0


def test_signed_backfill_rejects_forgery_conflicts_and_mutable_provenance():
    import copy,base64,os
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from backend.scripts.import_historical_upload_provenance import canonical,import_manifest
    db=LocalDatabase()
    document,public=trust_fixture_upload(db,'ois','owned/fixture.md',b'fixture','text/markdown',[{'owner_domain':'knowledge','parent_type':'item','parent_gid':'item-one'}])
    forged=copy.deepcopy(document);forged['manifest']['objects'][0]['owner_gid']='other'
    with patch.dict(os.environ,{'AI00_ATTACHMENT_BACKFILL_PUBLIC_KEY_PEM':public}),patch('backend.scripts.import_historical_upload_provenance.get_conn',return_value=db),patch('backend.platform_sdk.identity.get_conn',return_value=db):
        with pytest.raises(InvalidSignature):import_manifest(forged,apply=True)
        forged=copy.deepcopy(document);forged['manifest']['objects'][0]['sha256']='0'*64
        forged['signature']=base64.b64encode(Ed25519PrivateKey.from_private_bytes(bytes(range(1,33))).sign(canonical(forged['manifest']))).decode()
        with pytest.raises(ValueError,match='conflicting_upload_provenance'):import_manifest(forged,apply=True)
        forged['manifest']['signer_gid']='owner'
        forged['signature']=base64.b64encode(Ed25519PrivateKey.from_private_bytes(bytes(range(1,33))).sign(canonical(forged['manifest']))).decode()
        with pytest.raises(ValueError,match='active_administrator_required'):import_manifest(forged,apply=True)
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):db.db.execute("UPDATE workmanship_base_historical_uploads SET owner_gid='other'")
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):db.db.execute('DELETE FROM workmanship_base_historical_uploads')
    assert db.db.execute('SELECT COUNT(*) FROM workmanship_base_historical_uploads').fetchone()[0]==1
