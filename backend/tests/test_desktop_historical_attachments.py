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
        CREATE TABLE workmanship_auth_users(gid TEXT PRIMARY KEY,name TEXT,avatar_url TEXT,team_id TEXT,is_active INTEGER);
        INSERT INTO workmanship_auth_users VALUES('owner','Owner','','tenant',1);
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
        row=self.cursor_value.fetchone();return dict(row) if row else None
    def fetchall(self):return [dict(row) for row in self.cursor_value.fetchall()]


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
