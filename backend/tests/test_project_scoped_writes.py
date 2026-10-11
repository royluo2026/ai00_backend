from types import SimpleNamespace
from contextlib import contextmanager
from copy import deepcopy
import re
import pytest
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.project_management.project_management_backend.capabilities import register_capabilities
from plugins.project_management.project_management_backend.capabilities import scoped_writes as scoped


class Repo:
    def __init__(self):
        self.rows = {'project': {'gid': 'p', 'team_id': 't'}, 'task': {'project_gid': 'p', 'owner_user_gid': 'u'}, 'list': {'project_gid': 'p'}}
    def fetch_one(self, sql, params=()):
        if 'proj_projects' in sql: return self.rows['project']
        if 'work_lists' in sql: return self.rows['list']
        if 'proj_tasks' in sql: return self.rows['task']
        return None
    def fetch_all(self, sql, params=()): return []


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(scoped, 'get_active_identity_profile', lambda gid: {'gid': gid, 'team_id': 't'})
    monkeypatch.setattr(scoped, 'can_edit_project_bop', lambda *args: True)
    monkeypatch.setattr(scoped, 'entry_project_gid', lambda *args: None)
    monkeypatch.setattr(scoped, 'readable_entry_scope', lambda *args: None)
    return SimpleNamespace(user_gid='u', team_gid='t', active_roles=('member',))


def test_new_versions_leave_old_permissions_unchanged():
    registry = CapabilityRegistry(); register_capabilities(registry)
    for capability, old, new in scoped.VERSIONS:
        assert registry.get(capability, old).spec.permissions == ('project.manage_any',)
        entry = registry.get(capability, new)
        assert entry.spec.permissions == ('project.manage_assigned',)
        selector = entry.descriptor.resource_selectors[0]
        assert selector.resource_type == 'project' and selector.required
        assert entry.descriptor.business_invariants
        assert entry.descriptor.no_business_invariant_reason is None
        assert 'scoped_writes' in entry.descriptor.provider_ref


def test_manager_and_tenant_are_fresh(context, monkeypatch):
    repo = Repo()
    scoped.validate_scope(repo, {'project_gid': 'p', 'title': 'T'}, context, 'task', 'create')
    monkeypatch.setattr(scoped, 'can_edit_project_bop', lambda *args: False)
    with pytest.raises(CapabilityBusinessError):
        scoped.validate_scope(repo, {'project_gid': 'p'}, context, 'task', 'create')


@pytest.mark.parametrize('field,value', [('share_scope','team'), ('feishu_assignee_open_id','external'), ('bop_entry_gid','unknown'), ('related_knowledge_gid','unknown'), ('owner_user_gid','other')])
def test_external_scope_and_unresolved_domain_refs_denied(context, field, value):
    with pytest.raises(CapabilityBusinessError):
        scoped.validate_scope(Repo(), {'project_gid':'p', field:value}, context, 'issue', 'create')


def test_update_target_and_typed_parent_cannot_cross_project(context):
    repo=Repo(); repo.rows['task']['project_gid']='foreign'
    with pytest.raises(CapabilityBusinessError):
        scoped.validate_scope(repo, {'project_gid':'p','gid':'task','updates':{'title':'new'}}, context, 'task','update')
    with pytest.raises(CapabilityBusinessError):
        scoped.validate_scope(repo, {'project_gid':'p','parent_task_gid':'foreign'}, context, 'task','create')


def test_list_fk_and_actor_tenant_mismatch_denied(context):
    repo=Repo(); repo.rows['list']['project_gid']='foreign'
    with pytest.raises(CapabilityBusinessError): scoped.validate_scope(repo, {'project_gid':'p','list_gid':'l'}, context,'task','create')
    context.team_gid='other'
    with pytest.raises(CapabilityBusinessError): scoped.validate_scope(Repo(), {'project_gid':'p'},context,'task','create')


def test_update_cannot_preserve_external_sharing(context):
    repo=Repo(); repo.rows['task']['share_scope']='team'
    with pytest.raises(CapabilityBusinessError):
        scoped.validate_scope(repo, {'project_gid':'p','gid':'task','updates':{'title':'new'}},context,'task','update')


def test_reject_keeps_expected_revision_policy():
    registry=CapabilityRegistry(); register_capabilities(registry)
    old=registry.get('project.approval.order.reject',1).descriptor
    new=registry.get('project.approval.order.reject',2).descriptor
    assert new.concurrency_policy == old.concurrency_policy
    assert new.expected_version_payload_path == old.expected_version_payload_path


class SQLPort:
    """Small transactional SQL port; executes actual application/repository paths."""
    def __init__(self):
        self.tasks={}; self.operations={}; self.commits=0; self.rollbacks=0
        self.rows=[]; self.rowcount=0; self.fail_completion=False; self.calls=[]
        self.snapshot=({}, {})
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def cursor(self): return self
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows
    def execute(self,sql,params=()):
        self.calls.append((sql,params)); self.rows=[]; self.rowcount=1
        if 'SELECT gid,team_id FROM workmanship_proj_projects' in sql:
            self.rows=[{'gid':'p','team_id':'t'}]
        elif sql.startswith('INSERT INTO workmanship_proj_desktop_operations'):
            self.operations.setdefault(tuple(params[:4]), {'payload_hash':params[4], 'result_text':None})
        elif sql.startswith('SELECT payload_hash,result_text FROM workmanship_proj_desktop_operations'):
            self.rows=[self.operations[tuple(params)]]
        elif sql.startswith('UPDATE workmanship_proj_desktop_operations'):
            if self.fail_completion: raise RuntimeError('simulated replay persistence failure')
            self.operations[tuple(params[1:])]['result_text']=params[0]
        elif sql.startswith('INSERT INTO workmanship_proj_tasks '):
            columns=re.search(r'\(([^)]*)\)',sql).group(1).split(',')
            self.tasks[params[0]]=dict(zip(columns,params))
        elif sql.startswith('SELECT * FROM workmanship_proj_tasks'):
            row=self.tasks.get(params[0]); self.rows=[row] if row else []
        elif sql.startswith('SELECT user_gid') and 'workmanship_work_follows' in sql:
            self.rows=[]
        elif sql.startswith('UPDATE workmanship_proj_tasks SET '):
            assert sql.startswith('UPDATE workmanship_proj_tasks SET title=%s,updated_at=NOW()')
            self.tasks[params[-1]]['title']=params[0]
        elif sql.startswith('INSERT INTO workmanship_work_item_change_logs'):
            pass
        else:
            raise AssertionError('Unexpected SQL in scoped create test: '+sql)
        return self.rowcount
    def commit(self): self.commits+=1; self.snapshot=deepcopy((self.tasks,self.operations))
    def rollback(self): self.rollbacks+=1; self.tasks,self.operations=deepcopy(self.snapshot)


def test_actual_application_create_replays_once_and_rolls_back(context, monkeypatch):
    from backend.platform_sdk import ids
    monkeypatch.setattr(ids, 'next_display_id', lambda _:1)
    port=SQLPort()
    @contextmanager
    def connection(): yield port
    monkeypatch.setattr(scoped,'get_project_management_conn',connection)
    context.idempotency_key='key-1'
    handler=scoped.scoped_handler('project.task.change.apply.atomic.tasks_create',3,'task','create')
    payload={'arguments':{'project_gid':'p','title':'Scoped task','share_scope':'project'}}
    result=handler(payload,context)
    assert result['data']['data']['project_gid']=='p'
    assert len(port.tasks)==1 and port.commits==1
    assert handler(payload,context)==result and len(port.tasks)==1
    with pytest.raises(CapabilityBusinessError): handler({'arguments':{**payload['arguments'],'title':'different'}},context)
    assert len(port.tasks)==1
    context.idempotency_key='key-2'; port.fail_completion=True
    with pytest.raises(RuntimeError, match='replay persistence'): handler(payload,context)
    assert len(port.tasks)==1 and len(port.operations)==1 and port.rollbacks==2
    assert all('@3' in key[2] for key in port.operations)


def test_required_project_selector_contract():
    from jsonschema import Draft202012Validator
    registry=CapabilityRegistry(); register_capabilities(registry)
    for capability,old,new in scoped.VERSIONS:
        schema=registry.get(capability,new).descriptor.input_schema
        validator=Draft202012Validator(schema)
        args={'title':'T'} if capability.endswith('_create') else {'gid':'x','updates':{'title':'T'}} if capability.endswith('_update') else {'gid':'template','start_date':'2026-10-09'} if 'template' in capability else {'order_gid':'o','comment':'no','expected_revision':1}
        payload={'arguments':args} if 'atomic' in capability else args
        assert not validator.is_valid(payload)
        args['project_gid']='p'
        assert validator.is_valid(payload), list(validator.iter_errors(payload))


def test_rejection_replay_sql_uses_new_version_namespace():
    from plugins.project_management.project_management_backend.infrastructure.repository import _ApprovalRejectionTransaction
    class Cursor:
        def __init__(self): self.calls=[]
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql,params): self.calls.append(sql)
        def fetchone(self): return {'payload_hash':'hash','status':'pending'}
    cursor=Cursor()
    connection=SimpleNamespace(cursor=lambda:cursor)
    transaction=_ApprovalRejectionTransaction(scoped._RejectionConnection(connection))
    assert transaction.claim_approval_rejection(actor_gid='u',team_gid='t',idempotency_key='k',payload_hash='hash') is None
    assert len(cursor.calls)==2
    assert all('project.approval.order.reject@2' in sql and 'reject@1' not in sql for sql in cursor.calls)


def test_owner_resolved_craft_entry_must_match_target_project(context,monkeypatch):
    monkeypatch.setattr(scoped,'entry_project_gid',lambda gid,ctx:'p')
    scoped.validate_scope(Repo(),{'project_gid':'p','bop_entry_gid':'entry'},context,'issue','create')
    monkeypatch.setattr(scoped,'entry_project_gid',lambda gid,ctx:'foreign')
    with pytest.raises(CapabilityBusinessError): scoped.validate_scope(Repo(),{'project_gid':'p','bop_entry_gid':'entry'},context,'issue','create')


@pytest.mark.parametrize('scope,allowed', [
    ({'gid':'knowledge','source_project_gid':'p','share_scope':'project','creator_gid':'other'},True),
    ({'gid':'knowledge','source_project_gid':'foreign','share_scope':'global','creator_gid':'u'},False),
    ({'gid':'knowledge','source_project_gid':None,'share_scope':'global','creator_gid':'other'},True),
    ({'gid':'knowledge','source_project_gid':None,'share_scope':'personal','creator_gid':'u'},True),
    ({'gid':'knowledge','source_project_gid':None,'share_scope':'team','creator_gid':'other'},False),
    ({'gid':'different-entry','source_project_gid':'p','share_scope':'project','creator_gid':'u'},False),
])
def test_knowledge_entry_scope_and_public_rules(context,monkeypatch,scope,allowed):
    monkeypatch.setattr(scoped,'readable_entry_scope',lambda gid,ctx:scope)
    command={'project_gid':'p','related_knowledge_gid':'knowledge'}
    if allowed: scoped.validate_scope(Repo(),command,context,'issue','create')
    else:
        with pytest.raises(CapabilityBusinessError): scoped.validate_scope(Repo(),command,context,'issue','create')


def test_legacy_knowledge_item_is_not_an_entry(context,monkeypatch):
    def missing_entry(gid,ctx): raise CapabilityBusinessError('resource_not_found','No Knowledge entry exists.')
    monkeypatch.setattr(scoped,'readable_entry_scope',missing_entry)
    with pytest.raises(CapabilityBusinessError): scoped.validate_scope(Repo(),{'project_gid':'p','related_knowledge_gid':'legacy-item'},context,'issue','create')
    registry=CapabilityRegistry(); register_capabilities(registry)
    field=registry.get('project.issue.change.apply.atomic.issues_create',3).spec.input_schema['properties']['arguments']['properties']['related_knowledge_gid']
    assert 'Knowledge entry' in field['description'] and 'legacy' in field['description']


def test_actual_application_update_is_atomic(context,monkeypatch):
    port=SQLPort(); port.tasks['task']={'gid':'task','project_gid':'p','owner_user_gid':'u','share_scope':'project','title':'old'}
    port.snapshot=deepcopy((port.tasks,port.operations))
    @contextmanager
    def connection(): yield port
    monkeypatch.setattr(scoped,'get_project_management_conn',connection)
    context.idempotency_key='update-1'
    handler=scoped.scoped_handler('project.task.change.apply.atomic.tasks_update',3,'task','update')
    payload={'arguments':{'project_gid':'p','gid':'task','updates':{'title':'new'}}}
    assert handler(payload,context)=={'data':{'success':True}}
    assert port.tasks['task']['title']=='new' and port.commits==1
    assert handler(payload,context)=={'data':{'success':True}}
    context.idempotency_key='update-2'; port.fail_completion=True
    with pytest.raises(RuntimeError): handler({'arguments':{**payload['arguments'],'updates':{'title':'failed'}}},context)
    assert port.tasks['task']['title']=='new'


def test_template_map_is_explicitly_empty_and_rows_keep_real_owner():
    from jsonschema import Draft202012Validator
    registry=CapabilityRegistry(); register_capabilities(registry)
    descriptor=registry.get('project.task_template.change.apply.atomic.task_templates_instantiate',2).descriptor
    payload={'arguments':{'gid':'template','project_gid':'p','start_date':'2026-10-09','assignee_map':{'role':'u'}}}
    assert not Draft202012Validator(descriptor.input_schema).is_valid(payload)
    assert 'Independent task assignees' in descriptor.do_not_use_when
    port=SQLPort(); repo=scoped.ScopedRepository(port)
    repo.create_tasks_from_template([{'gid':'task','title':'T','description':'','owner_user_gid':'u','project_gid':'p','priority':'normal','share_scope':'team','template_item_gid':'item','template_source_version':1}])
    assert port.tasks['task']['owner_user_gid']=='u' and port.tasks['task']['share_scope']=='project'
    assert 'assignee_gid' not in port.tasks['task']
