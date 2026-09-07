import pytest
from jsonschema import Draft202012Validator
from backend.tests.support.desktop_round4_fixtures import execute


@pytest.mark.parametrize('index', range(5))
def test_actual_handler_outcomes_match_closed_contracts(index):
    row = execute()[index]
    Draft202012Validator(row['input_schema']).validate(row['payload'])
    Draft202012Validator(row['output_schema']).validate(row['provider_data'])
    assert not Draft202012Validator(row['input_schema']).is_valid({**row['payload'], '__unknown__':True})
