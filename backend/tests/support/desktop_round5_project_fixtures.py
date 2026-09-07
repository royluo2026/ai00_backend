"""A deterministic SQL driver exercises actual Project repository transactions."""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.project_management.project_management_backend.capabilities import register_capabilities
from plugins.project_management.project_management_backend.application import outcomes
from plugins.project_management.project_management_backend.application.service import ProjectManagementApplication
from plugins.project_management.project_management_backend.infrastructure.repository import ProjectManagementRepository


class Database:
    def __init__(self):
        self.orders={}; self.replays={}; self.notifications=[]; self.statements=[]; self.rows=[]; self.rowcount=1; self.commits=0; self.rollbacks=0
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def cursor(self): return self
    def commit(self): self.commits+=1
    def rollback(self): self.rollbacks+=1
    def execute(self,sql,params=()):
        self.statements.append(sql);self.rows=[];self.rowcount=1
        if sql.startswith('INSERT INTO workmanship_proj_desktop_operations'):
            self.replays.setdefault(tuple(params[:4]),{'payload_hash':params[4],'result_text':None})
        elif sql.startswith('SELECT payload_hash,result_text'): self.rows=[self.replays[tuple(params)]]
        elif sql.startswith('UPDATE workmanship_proj_desktop_operations'):
            self.replays[tuple(params[1:])]['result_text']=params[0]
        elif sql.startswith('INSERT INTO workmanship_proj_approval_orders'):
            fields=sql.split('(',1)[1].split(')',1)[0].split(',')
            row=dict(zip(fields,params));row.update(status='pending',revision=1,opinions=[])
            self.orders[row['gid']]=row
        elif sql.startswith('SELECT o.* FROM workmanship_proj_approval_orders'):
            if 'o.gid=%s' in sql:
                row=self.orders.get(params[0]);self.rows=[deepcopy(row)] if row and row['team_gid']==params[1] else []
            else: self.rows=[deepcopy(row) for row in self.orders.values() if row['team_gid']==params[0]]
        elif sql.startswith('UPDATE workmanship_proj_approval_orders SET status='):
            row=self.orders[params[2]]
            if row['revision']!=params[3]: self.rowcount=0
            else: row.update(status=params[0],revision=row['revision']+1,opinions=row['opinions']+json.loads(params[1]))
        elif sql.startswith('INSERT INTO workmanship_work_notifications'): self.notifications.append(tuple(params))
        elif sql.startswith('SELECT share_scope'): self.rows=[{'share_scope':'local'}]
        elif ' AS owner_gid FROM ' in sql: self.rows=[{'owner_gid':'reviewer'}]
        elif 'SELECT owner_gid,owner_type' in sql: self.rows=[{'owner_gid':'applicant','owner_type':'user'}]
        elif 'workmanship_work_list_shares' in sql and sql.startswith('SELECT'): self.rows=[{'gid':'share-one','list_gid':'list-one','shared_to':'reviewer','permission':'read','shared_by':'applicant','created_at':'2026-09-08'}]
        elif 'workmanship_work_lists' in sql and sql.startswith('SELECT'): self.rows=[{'owner_gid':'applicant','owner_type':'user','gid':'list-one','read_scope':'personal','write_scope':'personal','project_gid':None,'shared_team_gid':None}]
        return self.rowcount
    def fetchone(self): return deepcopy(self.rows[0]) if self.rows else None
    def fetchall(self): return deepcopy(self.rows)


def execute_project_matrix():
    database=Database();registry=CapabilityRegistry();rows=[]
    actor=lambda user,key:SimpleNamespace(user_gid=user,team_gid='fixture-team',active_roles=('super_admin',),idempotency_key=key,request_id=key)
    with ExitStack() as stack:
        stack.enter_context(patch('plugins.project_management.project_management_backend.infrastructure.desktop_repository.get_project_management_conn',return_value=database))
        stack.enter_context(patch('plugins.project_management.project_management_backend.infrastructure.repository.get_project_management_conn',return_value=database))
        stack.enter_context(patch('plugins.project_management.project_management_backend.data.connection.get_project_management_conn',return_value=database))
        stack.enter_context(patch('plugins.project_management.project_management_backend.capabilities.desktop_actions.find_active_user_by_role',return_value='reviewer'))
        stack.enter_context(patch('plugins.project_management.project_management_backend.capabilities.desktop_actions.get_user_summaries',return_value={'reviewer':{'name':'Reviewer','avatar_url':''}}))
        stack.enter_context(patch.object(outcomes.project_outcome_port,'provider',ProjectManagementApplication(ProjectManagementRepository())))
        register_capabilities(registry)
        def call(name,payload,user='applicant',key=None):
            entry=registry.get(name,1);offset=len(database.statements)
            result=entry.handler(payload,actor(user,key or name))
            rows.append({'id':name,'version':1,'payload':payload,'provider_data':result,'input_schema':entry.descriptor.input_schema,'output_schema':entry.descriptor.output_schema,'sql_statements':database.statements[offset:]})
            return result
        created=call('project.approval.order.create',{'title':'Fixture approval','reviewer_gid':'reviewer','content':{'description':'Fixture request'}})
        gid=created['data']['gid']
        call('project.approval.order.search',{})
        call('project.approval.order.get',{'order_gid':gid})
        call('project.approval.order.start',{'order_gid':gid,'expected_revision':1})
        call('project.approval.order.approve',{'order_gid':gid,'expected_revision':2,'comment':'Approved'},'reviewer')
        other=call('project.approval.order.create',{'title':'Withdraw fixture','reviewer_gid':'reviewer'},key='create-withdraw')['data']['gid']
        call('project.approval.order.withdraw',{'order_gid':other,'expected_revision':1})
        call('project.approval.scope_upgrade.create',{'item_type':'project','item_gid':'project-one','item_title':'Fixture project','current_scope':'local','target_scope':'team','reason':'Fixture'})
        call('project.follow.create',{'item_type':'project','item_gid':'project-one','item_title':'Fixture project'})
        call('project.share.list',{'list_gid':'list-one'})
        # Authorized empty history still executes the application's real scope and SQL checks.
        call('project.change_log.search',{'list_gid':'list-one','limit':100,'offset':0})
        replay=registry.get('project.approval.order.approve',1).handler({'order_gid':gid,'expected_revision':2,'comment':'Approved'},actor('reviewer','project.approval.order.approve'))
        assert replay['revision']==3 and len(database.notifications)==2
        assert database.orders[gid]['status']=='approved'
    return rows,database
