"""Real owner handlers and services with deterministic SQL/external I/O ports."""
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from jsonschema import Draft202012Validator
from backend.base.desktop_actions import DEFINITIONS, register_desktop_capabilities
from backend.capabilities.registry_next import CapabilityRegistry


PAYLOADS = {
    'base.team.create': {'name': 'Fixture team'},
    'base.team.update': {'team_gid': 'fixture-team', 'changes': {'name': 'Updated team'}},
    'base.team.archive': {'team_gid': 'fixture-team'},
    'base.team.member.list': {'team_gid': 'fixture-team'},
    'base.team.member.add': {'team_gid': 'fixture-team', 'member': {'user_gid': 'member-one'}},
    'base.team.member.remove': {'team_gid': 'fixture-team', 'user_gid': 'member-one'},
    'base.identity.current.get': {},
    'base.runtime.feature_flags.get': {},
    'base.runtime.feature_flags.replace': {'flags': [{'id': 'ai_assistant', 'enabled': True}, {'id': 'workbench', 'visibility': 'all', 'availability': 'all'}]},
    'base.runtime.annotation.search': {'collection': 'lists'},
    'base.runtime.capability_note.set': {'id': 'craft', 'value': 'Fixture note'},
    'base.runtime.capability_status.set': {'id': 'craft', 'value': 'active'},
    'base.runtime.list_note.set': {'id': 'task', 'value': 'Fixture list'},
    'base.runtime.feishu_app_id.get': {},
    'base.runtime.feishu_app_id.set': {'value': 'fixture-app'},
    'base.runtime.feishu_app_secret.set': {'value': 'fixture-secret'},
    'base.runtime.log.search': {'limit': 2},
    'base.file_store.minio_config.set': {'endpoint': 'https://storage.invalid', 'access_key': 'fixture-access', 'secret_key': 'fixture-secret', 'bucket': 'ai00'},
    'base.file_store.ois_config.set': {'identify': 'fixture', 'ois3_url': 'https://ois.invalid', 'idaas_client_secret': 'fixture-secret'},
    'base.file_store.minio_connection.test': {},
    'base.file_store.ois_connection.test': {},
    'base.feishu.calendar.day.get': {'date': '2026-09-08'},
    'base.feishu.calendar.event.get': {'event_id': 'event-one'},
    'base.feishu.calendar.event.update': {'event_id': 'event-one', 'changes': {'summary': 'Updated', 'description': 'Fixture'}},
    'base.feishu.calendar.rsvp.set': {'event_id': 'event-one', 'rsvp_status': 'accept'},
    **{'base.feishu.' + name + '.search': {'query': 'Fixture', 'limit': 5} for name in ('user', 'chat', 'document', 'event', 'meeting')},
    'base.feishu.organization_user.search': {'query': 'Fixture'},
    'base.feishu.list_share.send': {'chat_id': 'chat-one', 'list_name': 'Fixture list', 'share_url': 'https://app.invalid/share/list-one'},
}


def execute_base_matrix(invoke=None):
    registry = CapabilityRegistry()
    register_desktop_capabilities(registry)
    actor = {'gid': 'fixture-user', 'name': 'Fixture user', 'is_active': True, 'system_role': 'super_admin', 'org_role': 'super_admin', 'team_id': 'fixture-team'}
    context = SimpleNamespace(user_gid='fixture-user', team_gid='fixture-team', active_roles=('super_admin',))
    rows = []
    for capability_id, _, _, _, _, _, _ in DEFINITIONS:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        cursor.fetchone.return_value = {'key': 'feature_flags', 'value': '{"ai_assistant":true}', 'description': 'Fixture', 'updated_at': '2026-09-08', 'feishu_open_id': 'open-one'}
        cursor.fetchall.return_value = [{'gid': 'member-one', 'name': 'Fixture member', 'key': 'lists.task.note', 'value': 'Fixture note', 'description': '', 'created_at': '2026-09-08', 'email': '', 'avatar_url': '', 'org_role': 'member', 'feishu_open_id': 'open-one'}]
        record = {'name': 'Fixture record', 'summary': 'Fixture event', 'event_id': 'event-one', 'chat_id': 'chat-one', 'open_id': 'open-one', 'url': 'https://feishu.invalid/item', 'unknown_remote_secret': 'never-export'}
        with ExitStack() as stack:
            def port(target, **kwargs):
                return stack.enter_context(patch(target, **kwargs))
            port('backend.services.user_service.get_by_gid', return_value=deepcopy(actor))
            port('backend.routers.deps._get_user_grants', return_value=[])
            port('backend.services.user_service.get_feishu_token', return_value='server-only-fixture-token')
            for name in ('teams', 'admin', 'file_store', 'feishu_proxy'):
                port('backend.routers.' + name + '.get_conn', return_value=connection)
            port('backend.routers.teams.next_gid', return_value='created-team')
            port('backend.routers.admin._load_system_json', return_value={})
            saved_config = port('backend.routers.admin._save_system_json')
            port('backend.routers.admin.get_settings.cache_clear')
            port('backend.routers.file_store._load_system_json', return_value={})
            port('backend.routers.file_store._save_system_json')
            port('backend.core.storage.init_storage')
            port('backend.core.storage._get_minio_config', return_value={'endpoint': 'https://storage.invalid', 'bucket': 'ai00'})
            port('boto3.client', return_value=SimpleNamespace(head_bucket=lambda **kwargs: {}))
            port('backend.core.ois_storage._get_ois_config', return_value={'identify': 'fixture'})
            remote = SimpleNamespace(put_object=lambda *args: SimpleNamespace(is_succeed=lambda: True, data=SimpleNamespace(object_key='test/_connectivity_check.txt')))
            port('backend.core.ois_storage._make_client', return_value=(remote, None))
            port('backend.core.log_setup.get_recent_logs', return_value=['Fixture log'])
            port('backend.services.feishu_cache_service.search', return_value=[deepcopy(record)])
            port('backend.services.feishu_cache_service.needs_refresh', return_value=False)
            for name in ('get_calendar_today', 'search_chats', 'search_docs', 'search_users_by_name'):
                port('backend.services.feishu_service.feishu_service.' + name, return_value=[deepcopy(record)])
            port('backend.services.feishu_service.feishu_service.get_event_detail', return_value={'success': True, 'event': deepcopy(record)})
            for name in ('update_event', 'update_event_rsvp'):
                port('backend.services.feishu_service.feishu_service.' + name, return_value={'success': True, 'code': 0, 'msg': 'remote diagnostic'})
            port('backend.services.feishu_service.feishu_service.send_message_to_chat', return_value=True)
            entry = registry.get(capability_id, 1)
            payload = deepcopy(PAYLOADS[capability_id])
            result = invoke(entry,payload,context) if invoke else entry.handler(payload,context)
            Draft202012Validator(entry.descriptor.input_schema).validate(payload)
            Draft202012Validator(entry.descriptor.output_schema).validate(result)
            assert 'unknown_remote_secret' not in str(result)
            assert 'server-only-fixture-token' not in str(result)
            if capability_id == 'base.team.create':
                assert cursor.execute.call_args.args[1][0] == 'created-team'
                assert connection.commit.call_count == 1
            if capability_id == 'base.runtime.feishu_app_secret.set':
                assert saved_config.call_args.args[0]['feishu_config']['app_secret'] == 'fixture-secret'
            rows.append({'id': capability_id, 'version': 1, 'payload': payload, 'provider_data': result,
                         'input_schema': entry.descriptor.input_schema, 'output_schema': entry.descriptor.output_schema,
                         'sql_statements': len(cursor.execute.call_args_list), 'commits': connection.commit.call_count})
    return rows


if __name__ == '__main__':
    import json
    from pathlib import Path
    target = Path(__file__).resolve().parents[1] / 'fixtures/desktop_round5_base_outcomes.json'
    result = execute_base_matrix()
    target.write_text(json.dumps({'fixture_kind': 'Real registered handlers and actual owner services; deterministic SQL and external I/O ports, no live runtime approval', 'rows': result}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(result)} actual Base owner outcomes')
