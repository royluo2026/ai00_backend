"""Offline tests exercise the real provider SQL against a transactional port."""
from contextlib import contextmanager
from copy import deepcopy
from importlib import import_module, util
from types import SimpleNamespace
import json
import pytest

MODULE = 'plugins.craft.craft_backend.capabilities.entity_editor'


def test_paired_entity_editor_exists():
    assert util.find_spec(MODULE) is not None, 'The paired typed editor is missing'


class Port:
    def __init__(self):
        self.version = {'gid':'v', 'project_gid':'p', 'revision':3, 'status':'draft', 'frozen_at':None, 'archived_at':None, 'pbom_version_gid':'s'}
        self.link = {'link_gid':'l', 'entry_gid':'e', 'version_gid':'v', 'link_type':'bop_steps', 'entity_gid':'x', 'is_primary':True, 'snapshot_data':None, 'entry_title':'Entry'}
        self.entity = {'gid':'x', 'project_gid':'p', 'title':'Operation', 'op_req_height':42, 'vd_time':10, 'total_time':20, 'floor_height_need':1, 'params':{}, 'ext':{}, 'is_deleted':0, 'is_archived':0}
        self.ledger = {}; self.foreign = False; self.parent = None; self.snapshot_project = 'p'
        self.queries = []; self.writes = 0; self.commits = 0; self.rollbacks = 0; self.started = False; self.auto = True; self.fail_ledger = False

    @contextmanager
    def connection(self):
        yield self

    @contextmanager
    def cursor(self):
        yield Cursor(self)

    def get_autocommit(self): return self.auto
    def autocommit(self, value): self.auto = value
    def begin(self):
        assert not self.auto
        self.started = True
        self.saved = deepcopy((self.version, self.entity, self.ledger))
    def commit(self): self.commits += 1; self.started = False
    def rollback(self):
        self.rollbacks += 1
        if self.started: self.version, self.entity, self.ledger = self.saved
        self.started = False


class Cursor:
    def __init__(self, port): self.port = port; self.row = None; self.rowcount = 0
    def execute(self, sql, params=()):
        p = self.port; p.queries.append((sql, params)); self.rowcount = 0; self.row = None
        if sql.startswith('SELECT gid,project_gid,revision'):
            self.row = deepcopy(p.version) if params[0] == p.version['gid'] else None
        elif sql.startswith('SELECT l.gid AS link_gid'):
            self.row = deepcopy(p.link) if params == ('v', 'l') else None
        elif sql.startswith('SELECT result_json'):
            self.row = deepcopy(p.ledger.get(params[0]))
        elif sql.startswith('SELECT project_gid FROM workmanship_bop_pbom_versions'):
            self.row = {'project_gid':p.snapshot_project, 'status':'draft'}
        elif sql.startswith('SELECT parent_gid FROM workmanship_bop_pbom'):
            self.row = deepcopy(p.parent)
        elif sql.startswith('SELECT gid,project_gid FROM workmanship_bop_bop_station'):
            self.row = deepcopy(p.parent)
        elif sql.startswith('SELECT 1 FROM workmanship_bop_bop_entry_links'):
            self.row = {'found':1} if p.foreign else None
        elif sql.startswith('SELECT ') and ' WHERE gid=%s' in sql:
            self.row = deepcopy(p.entity) if params[0] == p.entity['gid'] else None
        elif sql.startswith('UPDATE workmanship_bop_bop_versions'):
            assert p.started and not p.auto
            if params == ('v', p.version['revision']):
                p.version['revision'] += 1; self.rowcount = 1; p.writes += 1
        elif sql.startswith('UPDATE workmanship_bop_'):
            assert p.started and not p.auto
            columns = [part.split('=')[0].strip(' `') for part in sql.split(' SET ',1)[1].split(' WHERE ',1)[0].split(',') if '%s' in part]
            p.entity.update(dict(zip(columns, params))); self.rowcount = 1; p.writes += 1
        elif sql.startswith('INSERT INTO workmanship_craft_bop_write_idempotency'):
            assert p.started and not p.auto
            if p.fail_ledger: raise RuntimeError('ledger failed')
            p.ledger[params[0]] = {'result_json':params[3], 'created_by':params[4], 'capability_id':params[1], 'version_gid':params[2]}
            self.rowcount = 1
        else:
            raise AssertionError('Unexpected SQL: ' + sql)
    def fetchone(self): return self.row


@pytest.fixture
def setup(monkeypatch):
    m = import_module(MODULE); port = Port()
    monkeypatch.setattr(m, 'get_craft_conn', port.connection)
    monkeypatch.setattr(m, 'get_active_identity_profile', lambda actor: {'gid':actor, 'team_id':'t'})
    monkeypatch.setattr(m, 'can_edit_project_bop', lambda *args: True)
    monkeypatch.setattr(m, 'list_user_project_memberships', lambda actor: [{'project_gid':'p'}])
    context = SimpleNamespace(user_gid='u', team_gid='t', permissions=('craft.read','craft.write'), active_roles=('super_admin',))
    return m, port, context


def snapshot(m, c, **extra):
    return m.get_edit_snapshot({'version_gid':'v', 'revision':3, 'link_gid':'l', **extra}, c).data


def patch_payload(m, c, **extra):
    data = snapshot(m, c)
    return {'version_gid':'v', 'expected_revision':3, 'link_gid':'l', 'expected_entity_token':data['entity_token'], 'idempotency_key':'request', 'fields':{'op_req_height':56}, **extra}


def test_full_operation_snapshot_not_card(setup):
    m,p,c = setup; data = snapshot(m,c)
    assert data['entity_data']['op_req_height'] == 42
    assert data['entity_data']['vd_time'] == 10
    assert data['entity_data']['total_time'] == 20
    assert data['entity_data']['floor_height_need'] == 1
    assert data['editability']['can_edit']
    assert 'project_gid' in data['readonly_fields']
    assert 'op_req_height' in data['editable_fields']
    assert p.writes == 0


def test_exact_link_no_first_global_resolution(setup):
    m,p,c = setup
    with pytest.raises(m.CapabilityBusinessError, match='resource_not_found'):
        snapshot(m,c,link_gid='wrong')
    assert all('ORDER BY l.is_primary' not in sql for sql,_ in p.queries)


def test_unbound_project_target_is_readonly(setup):
    m,p,c = setup
    data = m.get_edit_snapshot({'version_gid':'v','revision':3,'entity_type':'bop_steps','entity_gid':'x'},c).data
    assert data['link'] is None and not data['editability']['can_edit']
    assert data['editable_fields'] == []


def test_frozen_read_uses_snapshot_instead_of_live(setup):
    m,p,c = setup; p.version['frozen_at'] = '2026-01-01'
    p.link['snapshot_data'] = {'gid':'x','project_gid':'p','title':'Frozen','op_req_height':7,'unpublished_column':'hidden'}
    data = snapshot(m,c)
    assert data['entity_data']['title'] == 'Frozen' and data['entity_data']['op_req_height'] == 7
    assert data['target']['source'] == 'frozen_snapshot'
    assert 'unpublished_column' not in data['entity_data']
    assert not data['editability']['can_edit']
    assert not any('FROM workmanship_bop_bop_steps' in sql for sql,_ in p.queries)


def test_frozen_missing_snapshot_does_not_fallback(setup):
    m,p,c = setup; p.version['frozen_at'] = 'now'
    with pytest.raises(m.CapabilityBusinessError, match='snapshot_unavailable'): snapshot(m,c)


@pytest.mark.parametrize('field', ['gid','project_gid','bop_version_gid','version_no','source_type','source_ref_gid','owner_gid','created_by','is_deleted','is_archived','status'])
def test_mass_assignment_rejected(setup,field):
    m,p,c = setup; payload = patch_payload(m,c,fields={field:'evil'})
    with pytest.raises(m.CapabilityBusinessError, match='read_only_field'):
        m.patch_entity(payload,c)
    assert p.writes == 0


def test_same_connection_revision_mutation_and_durable_replay(setup):
    m,p,c = setup; payload = patch_payload(m,c)
    first = m.patch_entity(payload,c).data
    writes = p.writes
    second = m.patch_entity(payload,c).data
    assert first == second and p.writes == writes
    assert p.entity['op_req_height'] == 56 and p.version['revision'] == 4
    assert first['revision'] == 4 and p.auto
    envelope = json.loads(next(iter(p.ledger.values()))['result_json'])
    assert envelope['payload_hash'] and envelope['tenant_gid'] == 't'
    assert 'payload_hash' not in first and 'tenant_gid' not in first


def test_ledger_after_hash_uses_real_stored_timestamp(setup,monkeypatch):
    m,p,c=setup; payload=patch_payload(m,c)
    original=Cursor.execute
    def execute(cur,sql,params=()):
        result=original(cur,sql,params)
        if sql.startswith('UPDATE workmanship_bop_bop_steps'):
            p.entity['updated_at']='2026-10-10T00:00:01'
        return result
    monkeypatch.setattr(Cursor,'execute',execute)
    m.patch_entity(payload,c)
    envelope=json.loads(next(iter(p.ledger.values()))['result_json'])
    actual={key:p.entity.get(key) for key in m.TYPES['bop_steps'].columns}
    assert envelope['after_hash']==m.content_hash(actual)


def test_changed_payload_same_key_denied(setup):
    m,p,c = setup; payload = patch_payload(m,c); m.patch_entity(payload,c)
    payload['fields']['op_req_height'] = 100
    with pytest.raises(m.CapabilityBusinessError, match='idempotency_conflict'): m.patch_entity(payload,c)
    assert p.entity['op_req_height'] == 56


def test_ledger_failure_rolls_back_both_mutations(setup):
    m,p,c = setup; payload = patch_payload(m,c); p.fail_ledger = True
    with pytest.raises(RuntimeError, match='ledger failed'): m.patch_entity(payload,c)
    assert p.entity['op_req_height'] == 42 and p.version['revision'] == 3
    assert not p.ledger and p.rollbacks == 1 and p.auto


def test_entity_token_detects_concurrent_nonrevision_write(setup):
    m,p,c = setup; payload = patch_payload(m,c); p.entity['title'] = 'Concurrent'
    with pytest.raises(m.CapabilityBusinessError, match='entity_conflict'): m.patch_entity(payload,c)
    assert p.writes == 0


def test_revision_conflict_no_mutation(setup):
    m,p,c = setup; payload = patch_payload(m,c); p.version['revision'] = 4
    with pytest.raises(m.CapabilityBusinessError, match='revision_conflict'): m.patch_entity(payload,c)
    assert p.writes == 0


def test_revoked_manager_denied_even_replay_and_superadmin_claim(setup,monkeypatch):
    m,p,c = setup; payload = patch_payload(m,c); m.patch_entity(payload,c)
    monkeypatch.setattr(m,'can_edit_project_bop',lambda actor,project,line,roles: False)
    with pytest.raises(m.CapabilityBusinessError, match='permission_denied'): m.patch_entity(payload,c)


def test_tenant_mismatch_denied(setup):
    m,p,c = setup; c.team_gid='foreign'
    with pytest.raises(m.CapabilityBusinessError, match='permission_denied'): snapshot(m,c)


@pytest.mark.parametrize('foreign', ['target','binding','pbom'])
def test_foreign_project_refused(setup,foreign):
    m,p,c = setup
    if foreign == 'target': p.entity['project_gid']='other'
    elif foreign == 'binding': p.foreign=True
    else:
        p.link['link_type']='pbom_part'; p.entity={'gid':'x','snapshot_gid':'s','title':'Part','is_deleted':0}; p.snapshot_project='other'
    with pytest.raises(m.CapabilityBusinessError, match='permission_denied'): snapshot(m,c)


@pytest.mark.parametrize('kind', ['resource_tool','gbop','physical_equipment','issue','task_custom','rule_custom'])
def test_public_and_cross_owner_types_not_queried(setup,kind):
    m,p,c = setup; p.link['link_type']=kind
    with pytest.raises(m.CapabilityBusinessError, match='unsupported_entity_type'): snapshot(m,c)
    assert not any('workmanship_know_' in sql or 'workmanship_proj_' in sql or 'resource_requirements' in sql for sql,_ in p.queries)


def test_pbom_parent_fk_same_snapshot_and_no_cycle(setup):
    m,p,c = setup; p.link['link_type']='pbom_part'; p.entity={'gid':'x','snapshot_gid':'s','parent_gid':None,'title':'Part','is_deleted':0,'meta':{}}
    payload = patch_payload(m,c,fields={'parent_gid':'parent'})
    p.parent = None
    with pytest.raises(m.CapabilityBusinessError, match='invalid_reference'): m.patch_entity(payload,c)
    p.parent = {'parent_gid':'x'}
    with pytest.raises(m.CapabilityBusinessError, match='invalid_reference'): m.patch_entity(payload,c)
    assert p.writes == 0


def test_floor_height_station_fk_requires_same_project(setup):
    m,p,c = setup; p.link['link_type']='floor_height'; p.entity={'gid':'x','project_gid':'p','title':'Floor','height_mm':5,'is_deleted':0,'is_archived':0}
    payload = patch_payload(m,c,fields={'station_ref_gid':'station'})
    p.parent={'gid':'station','project_gid':'other'}
    with pytest.raises(m.CapabilityBusinessError, match='invalid_reference'): m.patch_entity(payload,c)
    assert p.writes == 0


def test_existing_station_reference_is_rechecked_when_other_field_changes(setup):
    m,p,c=setup; p.link['link_type']='floor_height'; p.entity={'gid':'x','project_gid':'p','title':'Floor','height_mm':5,'station_ref_gid':None,'is_deleted':0,'is_archived':0}
    payload=patch_payload(m,c,fields={'height_mm':10})
    p.entity['station_ref_gid']='foreign'; p.parent={'gid':'foreign','project_gid':'other'}
    payload['expected_entity_token']=m.content_hash({key:p.entity.get(key) for key in m.TYPES['floor_height'].columns})
    with pytest.raises(m.CapabilityBusinessError,match='invalid_reference'): m.patch_entity(payload,c)
    assert p.writes==0


@pytest.mark.parametrize('kind,field,reference', [('floor_height','station_ref_gid',{'gid':'parent','project_gid':'p'}),('pbom_part','parent_gid',{'parent_gid':None})])
def test_typed_local_references_can_commit(setup,kind,field,reference):
    m,p,c=setup; p.link['link_type']=kind
    p.entity={'gid':'x','project_gid':'p','snapshot_gid':'s','title':'Item','is_deleted':0,'is_archived':0,'meta':{}}
    payload=patch_payload(m,c,fields={field:'parent'}); p.parent=reference
    m.patch_entity(payload,c)
    assert p.entity[field]=='parent' and p.version['revision']==4


@pytest.mark.parametrize('alias', ['asm_line_process','asm_station_process','asm_operator_process','asm_operation','usesPart'])
def test_explicit_legacy_type_alias_uses_same_typed_owner_boundaries(setup,alias):
    m,p,c=setup; p.link['link_type']=alias
    p.entity={'gid':'x','project_gid':'p','snapshot_gid':'s','title':'Item','is_deleted':0,'is_archived':0,'meta':{}}
    payload=patch_payload(m,c,fields={'title':'Edited'})
    result=m.patch_entity(payload,c).data
    assert result['entity_type']==m.ALIASES[alias] and p.entity['title']=='Edited'


def test_json_nested_identity_assignment_refused(setup):
    m,p,c = setup; payload=patch_payload(m,c,fields={'ext':{'project_gid':'other'}})
    with pytest.raises(m.CapabilityBusinessError, match='read_only_field'): m.patch_entity(payload,c)
    assert p.writes == 0


def test_encoded_artifact_reference_requires_real_owner_authorization(setup,monkeypatch):
    from urllib.parse import quote
    m,p,c=setup; calls=[]
    ref={'artifact_id':'a','media_type':'image/png','sha256':'a'*64,'byte_size':4,'version':1}
    def reject(value,ctx):
        calls.append(value); raise PermissionError('not readable')
    monkeypatch.setattr(m,'require_artifact',reject,raising=False)
    payload=patch_payload(m,c,fields={'process_flow_pic':[{'url':'artifact:'+quote(json.dumps(ref),safe='')+'/pic.png'}]})
    with pytest.raises(m.CapabilityBusinessError,match='invalid_reference'): m.patch_entity(payload,c)
    assert calls==[ref] and p.writes==0


def test_authorized_artifact_reference_and_json_values_can_be_saved(setup,monkeypatch):
    m,p,c=setup; calls=[]
    ref={'artifact_id':'a','media_type':'image/png','sha256':'a'*64,'byte_size':4,'version':1}
    monkeypatch.setattr(m,'require_artifact',lambda value,ctx:calls.append(value) or value,raising=False)
    payload=patch_payload(m,c,fields={'process_flow_pic':[{'artifact_ref':ref}],'params':{'torque':{'minimum':1,'maximum':5}}})
    m.patch_entity(payload,c)
    assert calls==[ref]
    assert json.loads(p.entity['process_flow_pic'])==[{'artifact_ref':ref}]


def test_empty_typed_artifact_reference_cannot_bypass_owner_validation(setup):
    m,p,c=setup; payload=patch_payload(m,c,fields={'process_flow_pic':[{'artifact_ref':{}}]})
    with pytest.raises(m.CapabilityBusinessError,match='invalid_reference'): m.patch_entity(payload,c)
    assert p.writes==0


def test_experimental_closed_pair_registration():
    m=import_module(MODULE)
    from backend.capabilities.registry_next import CapabilityRegistry
    registry=CapabilityRegistry(); m.register_entity_editor_capabilities(registry)
    for capability in (m.READ_ID,m.WRITE_ID):
        entry=registry.get(capability,1)
        assert entry.descriptor.lifecycle_status.value == 'experimental'
        assert entry.spec.input_schema['additionalProperties'] is False
        assert entry.descriptor.provider_ref.endswith('entity_editor')
    write=registry.get(m.WRITE_ID,1).descriptor
    assert write.concurrency_policy == 'expected_version' and write.idempotency_policy == 'required'


def test_all_owner_mutable_types_have_explicit_closure():
    m=import_module(MODULE)
    expected={'bop_line','bop_station','bop_process','bop_steps','bop_operator','project_equipment','project_tooling','project_tools','project_roles','floor_height','control_plan','process_chart','jack_pos','pbom_part'}
    assert expected <= set(m.TYPES)
    for spec in m.TYPES.values():
        assert spec.table.startswith('workmanship_bop_')
        assert set(spec.editable).isdisjoint(spec.readonly)
        assert 'gid' in spec.readonly


def test_field_closure_matches_actual_mysql_owner_schema():
    import re
    from pathlib import Path
    m=import_module(MODULE)
    source=(Path(__file__).parents[1]/'db/mysql_schema.sql').read_text(encoding='utf-8')
    migrations='\n'.join(path.read_text(encoding='utf-8') for path in (Path(__file__).parents[1]/'db/migrations').rglob('*.sql'))
    for kind,spec in m.TYPES.items():
        block=re.search(r'CREATE TABLE IF NOT EXISTS '+spec.table+r' \((.*?)\) ENGINE=',source,re.S).group(1)
        columns=set(re.findall(r'^\s*([a-z][a-z0-9_]*)\s+(?:CHAR|TEXT|VARCHAR|JSON|TINYINT|DATETIME|INT|DECIMAL|DOUBLE)\b',block,re.M))
        for alter in re.findall(r'ALTER TABLE\s+`?'+spec.table+r'`?\s+([^;]+);',migrations,re.I):
            columns.update(re.findall(r'ADD COLUMN(?: IF NOT EXISTS)?\s+`?([a-z][a-z0-9_]*)',alter,re.I))
        assert set(spec.columns)==columns,(kind,set(spec.columns)-columns,columns-set(spec.columns))


def test_real_mysql_boolean_is_public_boolean(setup):
    from jsonschema import Draft202012Validator
    from backend.capabilities.registry_next import CapabilityRegistry
    m,p,c=setup; p.link['is_primary']=1
    registry=CapabilityRegistry(); m.register_entity_editor_capabilities(registry)
    Draft202012Validator(registry.get(m.READ_ID,1).descriptor.output_schema).validate(snapshot(m,c))


@pytest.mark.parametrize('field', ['ext','params','vpps_part'])
def test_nonnullable_columns_reject_null_before_sql(setup,field):
    m,p,c=setup; payload=patch_payload(m,c,fields={field:None})
    with pytest.raises(m.CapabilityBusinessError,match='invalid_input'): m.patch_entity(payload,c)
    assert p.writes==0


@pytest.mark.parametrize('kind', ['bop_line','bop_station','bop_process','bop_steps','bop_operator','project_equipment','project_tooling','project_tools','project_roles','floor_height','control_plan','process_chart','jack_pos','pbom_part'])
def test_each_declared_mutable_type_commits_a_real_business_field(setup,kind):
    m,p,c=setup; p.link['link_type']=kind
    p.entity={'gid':'x','project_gid':'p','snapshot_gid':'s','bop_version_gid':'v','title':'Old','name':'Old','is_deleted':0,'is_archived':0,'ext':{},'params':{},'meta':{}}
    field='name' if kind in {'bop_process','project_roles'} else 'title'
    payload=patch_payload(m,c,fields={field:'Edited'})
    result=m.patch_entity(payload,c).data
    assert p.entity[field]=='Edited' and result['entity_type']==kind
    assert result['revision']==4 and len(p.ledger)==1


def test_actual_craft_registration_and_gateway_pair(setup,monkeypatch):
    import asyncio
    from datetime import UTC,datetime
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.authorization import AuthorizationGrants
    from backend.capability_v2.catalog import CatalogResolver,build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.contracts import ActorIdentity,ConsumerDescriptor,ConsumerIdentity,ConsumerType,InvocationEnvelope,TenantIdentity
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.operations import InMemoryOperationStore,OperationService
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.capability_v2.reliability import ApprovalService,InMemoryApprovalStore,InMemoryRateLimiter,ReliabilityCoordinator
    from plugins.craft.craft_backend.capabilities import register_capabilities
    from backend.domain_ports.resource_authorization import resource_authorizers
    m,p,c=setup
    registry=CapabilityRegistry(); register_capabilities(registry)
    assert registry.get(m.READ_ID,1) and registry.get(m.WRITE_ID,1)
    release=build_release([item.descriptor for item in registry.snapshot()])
    catalog=InMemoryCatalogStore(); catalog.publish(release)
    policy=LegacyServerGatewayPolicy(user_loader=lambda actor:{'gid':actor,'is_active':True},grants_resolver=lambda identity,user:AuthorizationGrants(permissions=('craft.read','craft.write'),capability_scopes=(m.READ_ID,m.WRITE_ID),resource_scopes=('craft-bop-version:v',),data_scopes=('*',),policy_version='offline-test',tenant_id='t'),resource_authorizer=lambda ref,identity,user:resource_authorizers.authorize(ref,identity),approval_service=ApprovalService(InMemoryApprovalStore()))
    gateway=CapabilityGatewayService(CatalogResolver(catalog,registry),policy,reliability=ReliabilityCoordinator(InMemoryOutcomeStore(),InMemoryRateLimiter(limit=100)),operations=OperationService(InMemoryOperationStore())).bind_release(release.release_id)
    identity=ConsumerIdentity(actor=ActorIdentity(user_id='u',authentication_method='session',authenticated_at=datetime.now(UTC)),tenant=TenantIdentity(tenant_id='t',membership='member'),consumer=ConsumerDescriptor(type=ConsumerType.WEB,consumer_id='ai00.web'))
    def invoke(capability,payload,key=None):
        return asyncio.run(gateway.invoke(InvocationEnvelope(capability_id=capability,major_version=1,catalog_release=release.release_id,payload=payload,identity=identity,idempotency_key=key,expected_resource_version=str(payload['expected_revision']) if key else None,request_id='editor-test',trace_id='editor-trace')))
    read=invoke(m.READ_ID,{'version_gid':'v','revision':3,'link_gid':'l'})
    assert read.ok,read
    assert read.data['entity_data']['op_req_height']==42
    payload={'version_gid':'v','expected_revision':3,'link_gid':'l','expected_entity_token':read.data['entity_token'],'idempotency_key':'gateway-key','fields':{'op_req_height':60}}
    write=invoke(m.WRITE_ID,payload,'gateway-key')
    assert write.ok,write.error.model_dump() if write.error else write.model_dump()
    assert write.data['revision']==4 and p.entity['op_req_height']==60
    assert 'payload_hash' not in write.data
    writes=p.writes
    replay=invoke(m.WRITE_ID,payload,'gateway-key')
    assert replay.ok and replay.data==write.data and p.writes==writes
    monkeypatch.setattr(m,'can_edit_project_bop',lambda *args:False)
    revoked=invoke(m.WRITE_ID,payload,'gateway-key')
    assert not revoked.ok, 'A persisted Gateway replay bypassed revoked manager responsibility'
    denied=invoke(m.READ_ID,{'version_gid':'foreign','revision':3,'link_gid':'l'})
    assert not denied.ok and p.version['revision']==4
