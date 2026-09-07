"""Exact desktop Base actions execute the real registered owner handlers."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from jsonschema import Draft202012Validator
from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.official_provider import register_capabilities
from backend.tests.support.desktop_round5_fixtures import execute_base_matrix


def test_desktop_actions_are_real_closed_owner_registrations():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    for capability_id in (
        'base.team.create', 'base.team.update', 'base.team.archive',
        'base.team.member.list', 'base.team.member.add', 'base.team.member.remove',
        'base.identity.current.get', 'base.runtime.feature_flags.get',
        'base.runtime.feature_flags.replace', 'base.runtime.annotation.search',
        'base.runtime.capability_note.set', 'base.runtime.capability_status.set',
        'base.runtime.list_note.set', 'base.runtime.feishu_app_id.get',
        'base.runtime.feishu_app_id.set', 'base.runtime.feishu_app_secret.set',
        'base.runtime.log.search', 'base.file_store.minio_config.set',
        'base.file_store.ois_config.set', 'base.file_store.minio_connection.test',
        'base.file_store.ois_connection.test', 'base.feishu.calendar.day.get',
        'base.feishu.calendar.event.get', 'base.feishu.calendar.event.update',
        'base.feishu.calendar.rsvp.set', 'base.feishu.user.search',
        'base.feishu.chat.search', 'base.feishu.document.search',
        'base.feishu.event.search', 'base.feishu.meeting.search',
        'base.feishu.organization_user.search', 'base.feishu.list_share.send',
    ):
        entry = registry.get(capability_id, 1)
        assert entry is not None, capability_id
        assert entry.spec.owner == 'base'
        assert not Draft202012Validator(entry.descriptor.input_schema).is_valid({'owner_gid': 'attacker'})
        assert entry.descriptor.input_schema['additionalProperties'] is False
        assert entry.descriptor.output_schema['additionalProperties'] is False


def test_team_create_uses_authenticated_owner_and_real_sql():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    entry = registry.get('base.team.create', 1)
    assert entry is not None, 'exact team creation is not registered'
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    actor = {'gid': 'actor', 'system_role': 'super_admin', 'org_role': 'super_admin', 'is_active': True, 'team_id': 'team', 'grants': []}
    with patch('backend.services.user_service.get_by_gid', return_value=actor), patch('backend.routers.deps._get_user_grants', return_value=[]), patch('backend.routers.teams.get_conn', return_value=connection), patch('backend.routers.teams.next_gid', return_value='created-team'):
        value = entry.handler({'name': 'Real team'}, SimpleNamespace(user_gid='actor', team_gid='team', active_roles=('super_admin',)))
    assert value == {'success': True, 'data': {'gid': 'created-team', 'name': 'Real team'}}
    assert cursor.execute.call_args.args[1] == ('created-team', 'Real team', True, None, '{}')
    assert connection.commit.call_count == 1


def test_team_create_refuses_foreign_parent():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    entry = registry.get('base.team.create', 1)
    assert entry is not None, 'exact team creation is not registered'
    actor = {'gid': 'actor', 'system_role': 'member', 'org_role': 'member', 'is_active': True, 'team_id': 'team'}
    with patch('backend.services.user_service.get_by_gid', return_value=actor), patch('backend.routers.deps._get_user_grants', return_value=[]):
        with pytest.raises(Exception) as error:
            entry.handler({'name': 'Forbidden', 'parent_team_gid': 'foreign'}, SimpleNamespace(user_gid='actor', team_gid='team', active_roles=('member',)))
    assert error.value.code == 'permission_denied'


def test_every_real_base_handler_emits_a_closed_outcome():
    rows = execute_base_matrix()
    assert len(rows) == 32
    assert len({row['id'] for row in rows}) == 32


def test_every_administrative_action_refuses_non_admin_and_all_inputs_are_closed():
    from backend.base.desktop_actions import DEFINITIONS
    from backend.tests.support.desktop_round5_fixtures import PAYLOADS
    registry = CapabilityRegistry()
    register_capabilities(registry)
    actor = {'gid': 'actor', 'system_role': 'member', 'org_role': 'member', 'is_active': True, 'team_id': 'team'}
    context = SimpleNamespace(user_gid='actor', team_gid='team', active_roles=('member',))
    for capability_id, _, _, _, _, permission, _ in DEFINITIONS:
        entry = registry.get(capability_id, 1)
        with pytest.raises(Exception) as error:
            entry.handler({**PAYLOADS[capability_id], 'owner_gid': 'attacker'}, context)
        assert error.value.code == 'invalid_input'
        if permission != 'system.tech_config':
            continue
        with patch('backend.services.user_service.get_by_gid', return_value=actor), patch('backend.routers.deps._get_user_grants', return_value=[]):
            with pytest.raises(Exception) as error:
                entry.handler(PAYLOADS[capability_id], context)
        assert error.value.code == 'permission_denied', capability_id
