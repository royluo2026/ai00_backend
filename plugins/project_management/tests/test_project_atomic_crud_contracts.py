"""Project write descriptors describe real application acknowledgements."""
import copy

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.project_management.project_management_backend.application.outcomes import project_outcome_port
from plugins.project_management.project_management_backend.application.service import ProjectManagementApplication
from plugins.project_management.project_management_backend.capabilities.reviewed import register_reviewed_capabilities
from plugins.project_management.tests.test_project_application import InMemoryItemEntryRepository


@pytest.mark.parametrize('entity,action', [
    (entity, action) for entity in ('projects', 'vehicle_models') for action in ('create', 'update', 'delete')
])
def test_atomic_project_writes_validate_real_application_result(monkeypatch, entity, action):
    application = ProjectManagementApplication(InMemoryItemEntryRepository(), next_id=lambda: 'generated-1')
    monkeypatch.setattr(project_outcome_port, 'provider', application)
    context = CapabilityContext(user_gid='user-1', team_gid='team-1')
    create_arguments = {'project_code': 'EV', 'model_year': 2028, 'suffix': 'SOP'} if entity == 'projects' else {'name': 'Sedan'}
    if action != 'create':
        application.invoke('project.project.change.apply', {'operation': f'{entity}.create', 'arguments': create_arguments}, context)
    arguments = create_arguments if action == 'create' else {'gid': 'generated-1'}
    if action == 'update':
        arguments.update({'updates': {'suffix': 'PRE'}} if entity == 'projects' else {'name': 'Coupe'})
    registry = CapabilityRegistry()
    register_reviewed_capabilities(registry)
    entry = registry.get(f'project.project.change.apply.atomic.{entity}_{action}', 1)
    result = entry.handler({'arguments': arguments}, context)
    expected = {'success': True}
    if action == 'create':
        expected['data'] = {'gid': 'generated-1', 'name': 'EV-2028-SOP' if entity == 'projects' else 'Sedan'}
    assert result == {'data': expected}
    validate_payload(entry.spec.output_schema, result, label='output')
    unknown = copy.deepcopy(result)
    unknown['data']['unexpected'] = 'must remain closed'
    with pytest.raises(ValueError):
        validate_payload(entry.spec.output_schema, unknown, label='output')
    missing = copy.deepcopy(result)
    del missing['data']['success']
    with pytest.raises(ValueError):
        validate_payload(entry.spec.output_schema, missing, label='output')
    if action == 'create':
        unknown = copy.deepcopy(result)
        unknown['data']['data']['unexpected'] = 'must remain closed'
        with pytest.raises(ValueError):
            validate_payload(entry.spec.output_schema, unknown, label='output')
        for field in ('gid', 'name'):
            missing = copy.deepcopy(result)
            del missing['data']['data'][field]
            with pytest.raises(ValueError):
                validate_payload(entry.spec.output_schema, missing, label='output')
