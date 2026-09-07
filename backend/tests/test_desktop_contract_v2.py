import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities as craft
from plugins.project_management.project_management_backend.capabilities import register_capabilities as project

@pytest.fixture(scope='module')
def registry():
    result=CapabilityRegistry();craft(result);project(result);return result

BASE=json.loads((Path(__file__).parent/'fixtures/desktop_contract_v1.json').read_text())
@pytest.mark.parametrize('capability_id',BASE)
def test_v1_descriptor_is_immutable(registry,capability_id):
    assert registry.get(capability_id,1).descriptor.model_dump(mode='json')==BASE[capability_id]

@pytest.mark.parametrize('capability_id,payload',[
 ('craft.library.change.apply',{'operation':'tools.create','record':{'name':'Tool','vpps':'VPPS-1'}}),
 ('craft.rule.library.change.apply',{'operation':'create','record':{'name':'Rule','code':'R1','list_gid':None,'rule_definition':{}}}),
 ('project.task.change.apply.atomic.tasks_create',{'arguments':{'title':'Task','assignee_team_gid':None,'canvas_x':1.5,'completion':0}}),
 ('project.issue.change.apply.atomic.issues_create',{'arguments':{'title':'Issue','assignee_team_gid':None,'severity':'low','tracking_refs':[]}}),
])
def test_v2_accepts_model_fields_and_rejects_unknown_and_wrong_types(registry,capability_id,payload):
    entry=registry.get(capability_id,2)
    validator=Draft202012Validator(entry.descriptor.input_schema)
    validator.validate(payload)
    target=payload.get('record',payload.get('arguments'))
    target['__unknown__']='not allowed'
    assert list(validator.iter_errors(payload))
    del target['__unknown__']
    name='title' if 'arguments' in payload else 'name'
    target[name]=[]
    assert list(validator.iter_errors(payload))
    assert entry.spec.confirmation=='user'
    if capability_id != "craft.library.change.apply":
        assert entry.handler is registry.get(capability_id,1).handler

def test_v2_library_does_not_accept_fields_from_another_collection(registry):
    validator=Draft202012Validator(registry.get('craft.library.change.apply',2).descriptor.input_schema)
    assert list(validator.iter_errors({'operation':'tools.create','record':{'name':'Tool','category':'wrong collection'}}))
    assert list(validator.iter_errors({'operation':'tools.update','record':{'name':'Tool'}}))

def test_v2_pbom_batch_acceptance_matches_schema_and_real_handler(registry, monkeypatch):
    from types import SimpleNamespace
    from backend.tests.support.desktop_handler_fixtures import Connection
    from plugins.craft.craft_backend.capabilities import library_change
    entry = registry.get('craft.library.change.apply', 2)
    criteria = ' '.join(entry.descriptor.business_acceptance_criteria)
    assert 'part_names.batch_add_from_pbom' in criteria
    assert '500' in criteria and '10000' not in criteria
    payload = {'operation': 'part_names.batch_add_from_pbom', 'items': [{'vpps': ''}] * 500}
    validator = Draft202012Validator(entry.descriptor.input_schema)
    validator.validate(payload)
    assert not validator.is_valid({**payload, 'items': payload['items'] + [{'vpps': ''}]})
    connection = Connection()
    monkeypatch.setattr(library_change, 'get_conn', lambda: connection)
    outcome = entry.handler(payload, SimpleNamespace(user_gid='fixture-user', team_gid='fixture-team'))
    assert outcome.data == {'operation': payload['operation'], 'success': True, 'added': 0, 'skipped': 500}
    assert connection.commits == 1

@pytest.mark.parametrize('kind,model_name',[('task','TaskBody'),('issue','IssueBody')])
def test_v2_create_fields_exactly_match_authoritative_request_model(registry,kind,model_name):
    from plugins.craft.craft_backend.routers import promotion
    model=getattr(promotion,model_name)
    schema=registry.get(f'project.{kind}.change.apply.atomic.{kind}s_create',2).descriptor.input_schema
    assert set(schema['properties']['arguments']['properties'])==set(model.model_fields)
    Draft202012Validator(schema).validate({'arguments':model(title='Fixture').model_dump()})

@pytest.mark.parametrize('capability_id',BASE)
def test_v2_existing_success_projection_is_closed(registry,capability_id):
    data={'success':True,'data':{'gid':'fixture-gid'}}
    if capability_id=='craft.library.change.apply':data['operation']='tools.create'
    if capability_id.startswith('project.'):data={'data':data}
    validator=Draft202012Validator(registry.get(capability_id,2).descriptor.output_schema)
    validator.validate(data)
    target=data['data']['data'] if capability_id.startswith('project.') else data['data']
    target['__unknown__']='forbidden'
    assert list(validator.iter_errors(data))
