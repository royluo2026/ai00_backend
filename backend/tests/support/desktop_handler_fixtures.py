"""Actual Provider handlers with deterministic repository ports, never canned successes."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities as register_craft
from plugins.craft.craft_backend.capabilities import library_change
from plugins.project_management.project_management_backend.capabilities import register_capabilities as register_project
from plugins.project_management.project_management_backend.application.outcomes import project_outcome_port
from plugins.project_management.project_management_backend.application.service import ProjectManagementApplication

class Cursor:
    def __init__(self):self.rowcount=1;self.calls=[];self.found=None
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args):
        self.calls.append((sql,args));self.found={'gid':'existing'} if sql.startswith('SELECT') and args==('EXISTING',) else None
        self.rowcount=0 if args and args[-1]=='missing' else 1
    def fetchone(self):return self.found
class Connection:
    def __init__(self):self.port=Cursor();self.commits=0
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return self.port
    def commit(self):self.commits+=1
class Clock:
    @staticmethod
    def now(*args):return datetime(2026,9,8,0,0,tzinfo=timezone.utc)

def library_cases():
    result=[]
    for operation in library_change._OPERATIONS:
        collection,action=operation.split('.',1)
        payload={'operation':operation}
        if action in ('create','update'):
            payload['record']={'vpps':'VPPS-1','vpps_description':'Fixture part'} if collection=='part_names' else {'name':'Fixture '+collection}
        if action in ('update','delete','obsolete'):payload['gid']='fixture-gid'
        if action=='batch_add_from_pbom':payload.update(items=[{'vpps':'VPPS-1','vpps_desc_cn':'Fixture part','vpps_description':''},{'vpps':'EXISTING'},{'vpps':''}],meta={'added_by':'Fixture user','project':'Fixture project','added_at':'2026-09-08T00:00:00Z'})
        if action=='batch_accept_alias':payload.update(items=[{'vpps_part_gid':'fixture-gid','alias':'Fixture alias','pbom_part_gid':'pbom-one'},{'vpps_part_gid':'missing','alias':'Unmatched','pbom_part_gid':''}],meta={'added_by':'Fixture user','project':'Fixture project'})
        if action=='accept_alias':payload.update(gid='fixture-gid',alias='Fixture alias',record={'pbom_part_gid':'pbom-fixture'})
        result.append(payload)
    return result

def execute_library_matrix():
    registry=CapabilityRegistry();register_craft(registry);rows=[]
    for payload in library_cases():
        connection=Connection()
        with patch.object(library_change,'get_conn',return_value=connection),patch.object(library_change,'next_gid',return_value='created-gid'),patch.object(library_change,'datetime',Clock):
            entry=registry.get('craft.library.change.apply',2)
            value=entry.handler(deepcopy(payload),SimpleNamespace(user_gid='fixture-user',team_gid='fixture-team'))
        rows.append({'id':entry.spec.id,'version':2,'payload':payload,'provider_data':value.data,'statements':connection.port.calls,'commits':connection.commits})
    return registry,rows

class NotificationRepository:
    def __init__(self):self.items=[{'gid':'notification-one','type':'item_status','item_type':'task','item_gid':'task-one','title':'Fixture task changed','body':'Ready for review','is_read':False,'created_at':'2026-09-08 00:00:00'}]
    def list_notifications(self,user_gid,unread_only):return deepcopy([r for r in self.items if not unread_only or not r['is_read']])
    def count_unread_notifications(self,user_gid):return sum(not r['is_read'] for r in self.items)
    def mark_notification_read(self,gid,user_gid):
        for item in self.items:
            if item['gid']==gid:item['is_read']=True
    def mark_all_notifications_read(self,user_gid):
        for item in self.items:item['is_read']=True

def execute_notification_matrix():
    registry=CapabilityRegistry();register_project(registry);previous=project_outcome_port.provider
    project_outcome_port.bind(ProjectManagementApplication(NotificationRepository(),next_display_id=lambda _:1))
    rows=[]
    try:
        for operation,args in [('notifications_list',{'unread_only':False}),('notifications_unread_count',{}),('notifications_mark_read',{'gid':'notification-one'}),('notifications_unread_count',{}),('notifications_mark_all_read',{})]:
            prefix='project.notification.change.apply' if 'mark_' in operation else 'project.notification.read'
            entry=registry.get(prefix+'.atomic.'+operation,1);payload={'arguments':args}
            rows.append({'id':entry.spec.id,'version':1,'payload':payload,'provider_data':entry.handler(payload,SimpleNamespace(user_gid='fixture-user'))})
    finally:project_outcome_port.bind(previous)
    return rows

if __name__=='__main__':
    import json
    from pathlib import Path
    _,library=execute_library_matrix()
    target=Path(__file__).resolve().parents[1]/'fixtures/desktop_handler_outcomes.json'
    target.write_text(json.dumps({'fixture_kind':'Real registered handlers with deterministic SQL/repository ports; no live database or runtime approval','library':library,'notifications':execute_notification_matrix()},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
