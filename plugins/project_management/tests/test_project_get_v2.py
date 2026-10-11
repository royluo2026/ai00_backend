import json
from types import SimpleNamespace

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityBusinessError
from plugins.project_management.project_management_backend.capabilities.reviewed import register_reviewed_capabilities
from plugins.project_management.project_management_backend.application.outcomes import project_outcome_port
from plugins.project_management.project_management_backend.application.service import ProjectManagementApplication


@pytest.fixture
def project_read(monkeypatch):
    monkeypatch.setattr('backend.platform_sdk.access.build_access_scope',lambda user:{'team_gids':[user['team_id'],'10']})
    row=dict(gid='3',team_id='2',owner_gid='1',name='Project',status='active',share_scope='team',
        created_at='2026-09-28',updated_at='2026-09-28',meta={'zero':0,'empty':'','nil':None})
    monkeypatch.setattr(project_outcome_port,'provider',ProjectManagementApplication(SimpleNamespace(get_project=lambda gid:row if gid=='3' else None)))
    monkeypatch.setattr('backend.platform_sdk.project_access.can_manage_project',lambda *_:False)
    registry=CapabilityRegistry();register_reviewed_capabilities(registry)
    return registry,row


def test_project_read_v2_keeps_v1_frozen_and_returns_closed_real_application_data(project_read):
    registry,row=project_read
    v1=registry.get('project.project.read.atomic.projects_get',1)
    assert v1.spec.output_schema['properties']['data']=={'type':'object','properties':{},'additionalProperties':False}
    v2=registry.get('project.project.read.atomic.projects_get',2)
    payload={'arguments':{'gid':'3'}}
    validate_payload(v2.spec.input_schema,payload)
    result=v2.handler(payload,CapabilityContext(user_gid='1',team_gid='2',active_roles=('super_admin',)))
    validate_payload(v2.spec.output_schema,result,label='output')
    project=result['data']['data']
    assert project['gid']=='3' and project['team_id']=='2'
    assert json.loads(project['meta_json'])==row['meta'] and 'meta' not in project
    with pytest.raises(ValueError):validate_payload(v2.spec.input_schema,{'arguments':{'gid':'3','team_id':'99'}})


@pytest.mark.parametrize('foreign,private',[(True,False),(False,True)])
def test_project_read_v2_rejects_foreign_or_invisible_projects(project_read,foreign,private):
    registry,row=project_read
    if foreign:row['team_id']='99'
    if private:row.update(share_scope='personal',owner_gid='other')
    with pytest.raises(CapabilityBusinessError,match='project|Project'):
        registry.get('project.project.read.atomic.projects_get',2).handler({'arguments':{'gid':'3'}},CapabilityContext(user_gid='1',team_gid='2'))


@pytest.mark.parametrize('gid,code',[('missing','not_found'),(' ','invalid_input')])
def test_project_read_v2_declares_actual_application_errors(project_read,gid,code):
    registry,_=project_read;item=registry.get('project.project.read.atomic.projects_get',2)
    with pytest.raises(CapabilityBusinessError) as exc:
        item.handler({'arguments':{'gid':gid}},CapabilityContext(user_gid='1',team_gid='2'))
    assert exc.value.code==code
    assert code in {error.code for error in item.descriptor.domain_errors}
    v1=registry.get('project.project.read.atomic.projects_get',1)
    assert code not in {error.code for error in v1.descriptor.domain_errors}


def test_legacy_unowned_project_uses_only_the_authenticated_super_admin_tenant(project_read):
    registry,row=project_read;row['team_id']=None
    handler=registry.get('project.project.read.atomic.projects_get',2).handler
    result=handler({'arguments':{'gid':'3'}},CapabilityContext(user_gid='1',team_gid='2',active_roles=('super_admin',)))
    assert result['data']['data']['team_id']=='2' and row['team_id'] is None
    with pytest.raises(CapabilityBusinessError):handler({'arguments':{'gid':'3'}},CapabilityContext(user_gid='1',team_gid='2'))


def test_shared_parent_team_project_keeps_its_actual_ownership(project_read):
    registry,row=project_read;row['team_id']='10'
    result=registry.get('project.project.read.atomic.projects_get',2).handler(
        {'arguments':{'gid':'3'}},CapabilityContext(user_gid='1',team_gid='2'))
    assert result['data']['data']['team_id']=='10' and row['team_id']=='10'
