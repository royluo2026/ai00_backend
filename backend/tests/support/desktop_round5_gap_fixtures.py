"""Stateful SQL and Feishu ports; application and owner handlers are real."""
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.web_atomic import register_atomic_web_capabilities
from plugins.craft.craft_backend.capabilities import register_capabilities as register_craft
from plugins.knowledge.knowledge_backend.capabilities.reviewed import register_reviewed_capabilities
from plugins.project_management.project_management_backend.capabilities import register_capabilities as register_project


class Database:
    def __init__(self):
        self.rows=[];self.statements=[];self.rowcount=1;self.commits=0
        self.items={kind:{'gid':kind+'-one','title':'Before','owner_user_gid':'fixture-user','status':'open'} for kind in ('task','issue')}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return self
    def commit(self):self.commits+=1
    def rollback(self):pass
    def execute(self,sql,params=()):
        self.statements.append((sql,params));self.rows=[];self.rowcount=1
        if sql.startswith('SELECT parent_team_gid'):self.rows=[{'parent_team_gid':None}]
        elif 'FROM workmanship_auth_project_members' in sql:self.rows=[{'project_gid':'project-one'}]
        elif sql.startswith('SELECT gid FROM workmanship_auth_users'):self.rows=[{'gid':'fixture-user'}]
        elif 'FROM workmanship_auth_teams' in sql:self.rows=[{'gid':'team-one','feishu_dept_id':'department-one'}]
        elif 'COUNT(*) AS total' in sql:self.rows=[{'total':1}]
        elif sql.startswith('SELECT * FROM workmanship_auth_users'):self.rows=[{'gid':'fixture-user','system_role':'member'}]
        elif sql.startswith('SELECT') and 'workmanship_know_craft_rules' in sql:self.rows=[{'creator_gid':'fixture-user','owner_user_gid':'fixture-user','applicable_scope':{'team_gid':'fixture-team'}}]
        elif sql.startswith('SELECT') and 'workmanship_know_entries' in sql:self.rows=[{'creator_gid':'fixture-user','share_scope':'local'}]
        elif sql.startswith('SELECT') and 'workmanship_proj_projects' in sql:self.rows=[{'gid':'project-one','name':'Fixture project','status':'active','created_at':'2026-09-08','updated_at':'2026-09-08'}]
        elif sql.startswith('SELECT user_gid,notify_on'):self.rows=[{'user_gid':'follower-one','notify_on':['any_change']}]
        elif sql.startswith('SELECT') and 'workmanship_work_follows' in sql:self.rows=[{'gid':'follow-one','user_gid':'fixture-user','item_type':'project','item_gid':'project-one','item_title':'Fixture project','notify_on':['any_change'],'created_at':'2026-09-08'}]
        else:
            for kind,row in self.items.items():
                if f'workmanship_proj_{kind}s' in sql:
                    if sql.startswith('SELECT'):self.rows=[deepcopy(row)] if not params or params[0] in (row['gid'],'fixture-user') else []
                    elif sql.startswith('UPDATE'):
                        row['title']=params[0]
        return self.rowcount
    def fetchone(self):return deepcopy(self.rows[0]) if self.rows else None
    def fetchall(self):return deepcopy(self.rows)


def execute_gap_matrix(invoke=None):
    db=Database();registry=CapabilityRegistry();rows=[]
    register_atomic_web_capabilities(registry);register_craft(registry);register_reviewed_capabilities(registry);register_project(registry)
    context=SimpleNamespace(user_gid='fixture-user',team_gid='fixture-team',active_roles=('super_admin',),permissions=('knowledge.manage','project.manage_any','craft.rule.write'))
    with ExitStack() as stack:
        for target in ('backend.services.org_sync_service.get_conn','backend.services.user_service.get_conn','backend.platform_sdk.access.get_conn','plugins.project_management.project_management_backend.infrastructure.repository.get_project_management_conn','plugins.craft.craft_backend.capabilities.rule_library.get_conn','plugins.knowledge.knowledge_backend.infrastructure.repository.get_knowledge_conn'):
            stack.enter_context(patch(target,return_value=db))
        stack.enter_context(patch('backend.services.org_sync_service.feishu_service.sync_org_structure',return_value={'departments':[{'open_id':'department-one','name':'Fixture department'}],'users':[{'open_id':'feishu-user','name':'Fixture user','email':'fixture@example.invalid','avatar_url':'','department_open_ids':['department-one']}]}))
        def call(name,payload,version=1):
            entry=registry.get(name,version);before=len(db.statements)
            data=invoke(entry,payload,context) if invoke else entry.handler(payload,context)
            rows.append({'id':name,'version':version,'payload':payload,'provider_data':data,'input_schema':entry.descriptor.input_schema,'output_schema':entry.descriptor.output_schema,'sql_statements':db.statements[before:]})
            return data
        result=call('base.identity.directory.feishu.sync',{})
        assert result['updated']==1 and result['dept_synced']==1 and result['departments']==1
        call('craft.rule.library.change.apply',{'operation':'update','gid':'rule-one','record':{'name':'Updated rule'}},2)
        assert call('knowledge.entry.change.apply.atomic.entries_update',{'gid':'entry-one','updates':{'title':'Updated knowledge'}})=={'data':{'changed':True}}
        for kind in ('task','issue'):
            assert call(f'project.{kind}.change.apply.atomic.{kind}s_update',{'arguments':{'gid':kind+'-one','updates':{'title':'Updated '+kind}}},2)=={'data':{'success':True}}
            assert db.items[kind]['title']=='Updated '+kind
        call('project.project.read.atomic.projects_search',{'arguments':{'include_deleted':False,'include_archived':False}})
        call('project.follow.read.atomic.follows_list',{'arguments':{}})
        for kind in ('task','issue'):
            result=call(f'project.{kind}.read.atomic.{kind}s_search',{'arguments':{'page_size':200}})
            assert result['data']['data'][0]['title']=='Updated '+kind
        assert any('workmanship_work_item_change_logs' in sql for sql,_ in db.statements)
        assert any('INSERT INTO workmanship_work_notifications' in sql for sql,_ in db.statements)
    return rows
