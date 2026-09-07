import pytest
from jsonschema import Draft202012Validator
from backend.tests.support.desktop_handler_fixtures import execute_library_matrix, execute_notification_matrix

@pytest.mark.parametrize('index',range(19))
def test_library_registered_handler_accepts_request_and_emits_closed_result(index):
    registry,rows=execute_library_matrix();row=rows[index];entry=registry.get(row['id'],2)
    Draft202012Validator(entry.descriptor.input_schema).validate(row['payload'])
    Draft202012Validator(entry.descriptor.output_schema).validate(row['provider_data'])
    assert row['provider_data']['operation']==row['payload']['operation']
    assert row['commits']==1
    assert row['statements']

def test_notification_actual_application_outcomes():
    rows=execute_notification_matrix()
    assert rows[0]['provider_data']['data']['data'][0]['gid']=='notification-one'
    assert rows[1]['provider_data']['data']['data']['count']==1
    assert rows[3]['provider_data']['data']['data']['count']==0

@pytest.mark.parametrize('index',range(19))
def test_library_operation_property_matrix_rejects_unknown_and_wrong_result(index):
    from copy import deepcopy
    registry,rows=execute_library_matrix();row=rows[index];entry=registry.get(row['id'],2)
    request=Draft202012Validator(entry.descriptor.input_schema)
    result=Draft202012Validator(entry.descriptor.output_schema)
    invalid=deepcopy(row['payload']);invalid['undeclared']=True
    assert not request.is_valid(invalid)
    invalid=deepcopy(row['provider_data']);invalid['undeclared']=True
    assert not result.is_valid(invalid)
    invalid=deepcopy(row['provider_data']);invalid['success']='true'
    assert not result.is_valid(invalid)
    invalid=deepcopy(row['provider_data']);del invalid['operation']
    assert not result.is_valid(invalid)

def test_library_arbitrary_nested_json_stays_closed():
    registry,_=execute_library_matrix();validator=Draft202012Validator(registry.get('craft.library.change.apply',2).descriptor.input_schema)
    assert not validator.is_valid({'operation':'tools.create','record':{'name':'Tool','spec':{'undeclared':1}}})
    assert not validator.is_valid({'operation':'part_names.create','record':{'vpps':'V','meta':{'undeclared':1}}})

def test_library_schema_operations_equal_real_handler_operations():
    from plugins.craft.craft_backend.capabilities.library_change import _OPERATIONS
    registry,_=execute_library_matrix();descriptor=registry.get('craft.library.change.apply',2).descriptor
    assert {x['properties']['operation']['const'] for x in descriptor.input_schema['oneOf']}==set(_OPERATIONS)
    assert {x['properties']['operation']['const'] for x in descriptor.output_schema['oneOf']}==set(_OPERATIONS)
