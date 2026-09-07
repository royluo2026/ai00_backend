"""Closed Base desktop outcomes. Each binding selects one owner operation.

Compatibility functions remain the authoritative Base implementations; neither a
URL, a method nor a caller-supplied principal is accepted at this boundary.
"""
from __future__ import annotations

import json
from functools import wraps
from typing import Any

from jsonschema import Draft202012Validator
from fastapi import HTTPException
from backend.capability_v2.atomic_web_contracts import obj
from backend.capability_v2.contracts import BusinessInvariantContract, ExposurePolicy
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec

TEXT = {'type': 'string', 'maxLength': 4096}
ID = {'type': 'string', 'minLength': 1, 'maxLength': 256}
BOOL = {'type': 'boolean'}
NULL_TEXT = {'type': ['string', 'null'], 'maxLength': 4096}
OK = obj({'success': {'const': True}}, ('success',))


def array(item, maximum=500):
    return {'type': 'array', 'items': item, 'maxItems': maximum}


def response(data):
    return obj({'success': {'const': True}, 'data': data}, ('success', 'data'))


def strings(*fields):
    return obj({key: TEXT for key in fields}, fields)


def select(row, schema):
    """Project external records onto a finite public model, without credentials."""
    result = {}
    for key, field in schema['properties'].items():
        value = row.get(key)
        kind = field.get('type')
        if kind == 'boolean':
            result[key] = bool(value)
        elif kind == 'integer':
            result[key] = int(value or 0)
        elif kind == 'array':
            result[key] = list(value or [])[:field['maxItems']]
        elif isinstance(kind, list) and value is None:
            result[key] = None
        else:
            result[key] = str(value or '')[:field.get('maxLength', 4096)]
    return result


def _actor(context):
    from backend.services import user_service
    from backend.routers.deps import build_profile
    user = user_service.get_by_gid(str(context.user_gid))
    if not user or not user.get('is_active'):
        raise CapabilityBusinessError('permission_denied', 'The authenticated user is inactive.')
    tenant = str(user.get('team_id') or f'user:{context.user_gid}')
    if getattr(context, 'team_gid', None) and tenant != str(context.team_gid):
        raise CapabilityBusinessError('permission_denied', 'The authenticated tenant has changed.')
    return build_profile(dict(user))


def _super(actor):
    if 'super_admin' not in {actor.get('org_role'), actor.get('system_role')}:
        raise CapabilityBusinessError('permission_denied', 'A super administrator is required.')


def _success(value):
    if value.get('success') is not True:
        raise CapabilityBusinessError('dependency_failed', 'The external service did not complete the operation.', retryable=False)
    return value


def create_team(payload, actor):
    from backend.routers.teams import CreateTeamBody, create_team as service
    return service(CreateTeamBody(**payload), current_user=actor)


def update_team(payload, actor):
    from backend.routers.teams import UpdateTeamBody, update_team as service
    _super(actor)
    return service(payload['team_gid'], UpdateTeamBody(**payload['changes']), _=actor)


def archive_team(payload, actor):
    from backend.routers.teams import delete_team
    _super(actor)
    return delete_team(payload['team_gid'], _=actor)


MEMBER = obj({**{key: TEXT for key in ('gid', 'name', 'email', 'avatar_url', 'org_role', 'created_at')}}, ('gid', 'name', 'email', 'avatar_url', 'org_role', 'created_at'))


def list_team_members(payload, actor):
    from backend.routers.teams import list_team_members as service
    result = service(payload['team_gid'], current_user=actor)
    return {'success': True, 'data': [select(row, MEMBER) for row in result['data'][:500]]}


def add_team_member(payload, actor):
    from backend.routers.teams import AddMemberBody, add_team_member as service
    return service(payload['team_gid'], AddMemberBody(**payload['member']), current_user=actor)


def remove_team_member(payload, actor):
    from backend.routers.teams import remove_team_member as service
    return service(payload['team_gid'], payload['user_gid'], current_user=actor)


GRANT = obj({**{key: NULL_TEXT for key in ('gid', 'scope_gid', 'granted_at', 'expires_at', 'note')}, 'grant_type': ID}, ('grant_type',))
PROFILE = obj({**{key: NULL_TEXT for key in ('gid', 'name', 'email', 'avatar_url', 'system_role', 'org_role', 'external_subtype', 'team_id', 'created_at', 'updated_at')}, 'is_active': BOOL, 'permissions': array(ID, 500), 'visible_panels': array(ID, 100), 'grants': array(GRANT)}, ('gid', 'name', 'system_role', 'org_role', 'permissions', 'grants', 'visible_panels', 'is_active'))


def current_identity(_payload, actor):
    profile = select(actor, PROFILE)
    profile['grants'] = [select(row, GRANT) for row in actor.get('grants', [])[:500]]
    return {'success': True, 'data': profile}


CONFIG = obj({'key': ID, 'value': NULL_TEXT, 'description': NULL_TEXT, 'updated_at': NULL_TEXT, 'source': {'type': 'string', 'enum': ['env', 'db']}}, ('key', 'value'))
FLAG = obj({'id': ID, 'enabled': BOOL, 'visibility': TEXT, 'availability': TEXT}, ('id',))


def get_flags(_payload, _actor):
    from backend.routers.admin import get_config
    value = get_config('feature_flags', _=_actor)['data']
    return {'success': True, 'data': {**select(value, CONFIG), 'source': value.get('source', 'db')}}


def replace_flags(payload, actor):
    _super(actor)
    from backend.routers.admin import set_config, ConfigBody
    flags = {}
    for row in payload['flags']:
        if row['id'] in flags:
            raise CapabilityBusinessError('invalid_input', 'A feature flag occurs more than once.')
        values = {key: value for key, value in row.items() if key != 'id'}
        flags[row['id']] = values['enabled'] if set(values) == {'enabled'} else values
    set_config('feature_flags', ConfigBody(value=json.dumps(flags, ensure_ascii=False)), _=actor)
    return {'success': True}


def annotation_search(payload, actor):
    _super(actor)
    from backend.routers.admin import list_config
    prefix = payload.get('collection', 'capabilities') + '.'
    rows = list_config(_=actor)['data']
    data = [{**select(row, CONFIG), 'source': 'db'} for row in rows if row['key'].startswith(prefix)][:500]
    return {'success': True, 'data': data}


def set_capability_note(payload, actor):
    return _annotation_set('capabilities', 'note', payload, actor)


def set_capability_status(payload, actor):
    return _annotation_set('capabilities', 'status', payload, actor)


def set_list_note(payload, actor):
    return _annotation_set('lists', 'note', payload, actor)


def _annotation_set(collection, field, payload, actor):
    _super(actor)
    from backend.routers.admin import set_config, ConfigBody
    set_config(f'{collection}.{payload["id"]}.{field}', ConfigBody(value=payload['value']), _=actor)
    return {'success': True}


def get_feishu_app_id(_payload, actor):
    _super(actor)
    from backend.routers.admin import get_config
    data = get_config('FEISHU_APP_ID', _=actor)['data']
    return {'success': True, 'data': {**select(data, CONFIG), 'source': data.get('source', 'db')}}


def set_feishu_app_id(payload, actor):
    _super(actor)
    from backend.routers.admin import set_config, ConfigBody
    set_config('FEISHU_APP_ID', ConfigBody(value=payload['value']), _=actor)
    return {'success': True}


def set_feishu_app_secret(payload, actor):
    _super(actor)
    from backend.routers.admin import set_config, ConfigBody
    set_config('FEISHU_APP_SECRET', ConfigBody(value=payload['value']), _=actor)
    return {'success': True}


def search_logs(payload, actor):
    _super(actor)
    from backend.core.log_setup import get_recent_logs
    # The log service already returns formatted strings; bound each result.
    return {'success': True, 'data': [str(value)[:4096] for value in get_recent_logs(payload.get('limit', 200))]}


def save_minio(payload, actor):
    _super(actor)
    from backend.routers.file_store import save_config
    _success(save_config(payload, _user=actor))
    return {'success': True}


def save_ois(payload, actor):
    _super(actor)
    from backend.routers.file_store import save_ois_config
    _success(save_ois_config(payload, _user=actor))
    return {'success': True}


CONNECTION = obj({'success': BOOL, 'msg': TEXT}, ('success', 'msg'))


def test_minio(_payload, actor):
    _super(actor)
    from backend.routers.file_store import test_connection
    result = test_connection({}, _user=actor)
    return {'success': bool(result['success']), 'msg': '连接成功' if result['success'] else '连接失败，请检查服务端配置'}


def test_ois(_payload, actor):
    _super(actor)
    from backend.routers.file_store import test_ois_connection
    result = test_ois_connection({}, _user=actor)
    return {'success': bool(result['success']), 'msg': '连接成功' if result['success'] else '连接失败，请检查服务端配置'}


USER = strings('open_id', 'name', 'email', 'avatar_url', 'entity_id', 'db_gid')
CHAT = strings('chat_id', 'name', 'avatar', 'description', 'entity_id', 'url')
DOCUMENT = strings('name', 'url', 'type', 'owner_name', 'entity_id')
EVENT = obj({**{key: TEXT for key in ('event_id', 'summary', 'description', 'start', 'end', 'start_ts', 'end_ts', 'rsvp', 'meeting_url', 'organizer')}, 'is_organizer': BOOL}, ('event_id', 'summary', 'description', 'start', 'end', 'start_ts', 'end_ts', 'rsvp', 'meeting_url', 'organizer', 'is_organizer'))
SEARCH_EVENT = strings('name', 'url', 'entity_id', 'start_time', 'end_time', 'description', 'event_id', 'summary')
MEETING = strings('name', 'url', 'entity_id', 'start_time', 'end_time', 'description', 'meeting_id')
SEARCH = obj({'query': TEXT, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50}}, ('query',))


def calendar_day(payload, actor):
    from backend.routers.feishu_proxy import get_calendar_today
    result = _success(get_calendar_today(date=payload.get('date'), current_user=actor))
    return {'success': True, 'data': [select(row, EVENT) for row in result['data'][:500]]}


def event_get(payload, actor):
    from backend.routers.feishu_proxy import get_event_detail
    result = _success(get_event_detail(payload['event_id'], current_user=actor))
    return {'success': True, 'event': select(result['event'], strings('event_id', 'summary', 'description'))}


def event_update(payload, actor):
    from backend.routers.feishu_proxy import update_event, EventUpdateBody
    _success(update_event(payload['event_id'], EventUpdateBody(**payload['changes']), current_user=actor))
    return {'success': True}


def event_rsvp(payload, actor):
    from backend.routers.feishu_proxy import update_event_rsvp, EventRsvpBody
    _success(update_event_rsvp(payload['event_id'], EventRsvpBody(rsvp_status=payload['rsvp_status']), current_user=actor))
    return {'success': True}


def _search(service, schema, payload, actor):
    value = _success(service(q=payload['query'], limit=payload.get('limit', 10), background_tasks=None, current_user=actor))
    return {'success': True, 'data': [select(row, schema) for row in value['data'][:payload.get('limit', 10)]]}


def user_search(payload, actor):
    from backend.routers.feishu_proxy import search_feishu_users
    return _search(search_feishu_users, USER, payload, actor)


def chat_search(payload, actor):
    from backend.routers.feishu_proxy import search_feishu_chats
    return _search(search_feishu_chats, CHAT, payload, actor)


def document_search(payload, actor):
    from backend.routers.feishu_proxy import search_feishu_docs
    return _search(search_feishu_docs, DOCUMENT, payload, actor)


def event_search(payload, actor):
    from backend.routers.feishu_proxy import search_feishu_events
    return _search(search_feishu_events, SEARCH_EVENT, payload, actor)


def meeting_search(payload, actor):
    from backend.routers.feishu_proxy import search_feishu_meetings
    return _search(search_feishu_meetings, MEETING, payload, actor)


def organization_user_search(payload, actor):
    from backend.routers.feishu_proxy import search_org_users
    result = _success(search_org_users(q=payload['query'], current_user=actor))
    return {'success': True, 'data': [select(row, USER) for row in result['data'][:15]]}


def list_share_send(payload, actor):
    from backend.routers.feishu_proxy import share_list_to_chat, ShareListBody
    _success(share_list_to_chat(ShareListBody(**payload), current_user=actor))
    return {'success': True}


# id, real handler, input, output, write, permission, effect. No runtime selector.
DEFINITIONS = [
    ('base.team.create', create_team, obj({'name': ID, 'is_active': BOOL, 'parent_team_gid': NULL_TEXT}, ('name',)), response(strings('gid', 'name')), True, 'system.user.manage', 'Creates one team under a parent the authenticated administrator controls.'),
    ('base.team.update', update_team, obj({'team_gid': ID, 'changes': {**obj({'name': ID, 'is_active': BOOL}), 'minProperties': 1}}, ('team_gid', 'changes')), OK, True, 'system.user.manage', 'Changes the name or active state of one team under super administrator authorization.'),
    ('base.team.archive', archive_team, obj({'team_gid': ID}, ('team_gid',)), OK, True, 'system.user.manage', 'Soft deletes one team while preserving its stored history.'),
    ('base.team.member.list', list_team_members, obj({'team_gid': ID}, ('team_gid',)), response(array(MEMBER)), False, '', 'Returns at most 500 members of a team the current user may view.'),
    ('base.team.member.add', add_team_member, obj({'team_gid': ID, 'member': obj({'user_gid': NULL_TEXT, 'feishu_open_id': NULL_TEXT, 'name': NULL_TEXT, 'email': NULL_TEXT, 'avatar_url': NULL_TEXT})}, ('team_gid', 'member')), OK, True, 'system.user.manage', 'Assigns one existing or identified Feishu user to a team the administrator controls.'),
    ('base.team.member.remove', remove_team_member, obj({'team_gid': ID, 'user_gid': ID}, ('team_gid', 'user_gid')), OK, True, 'system.user.manage', 'Removes one member from a team the administrator controls.'),
    ('base.identity.current.get', current_identity, obj({}), response(PROFILE), False, '', 'Returns the active user profile and current grants without credentials.'),
    ('base.runtime.feature_flags.get', get_flags, obj({}), response(CONFIG), False, '', 'Reads the current UI feature configuration without exposing other system configuration.'),
    ('base.runtime.feature_flags.replace', replace_flags, obj({'flags': array(FLAG)}, ('flags',)), OK, True, 'system.tech_config', 'Replaces the typed UI feature configuration and invalidates the runtime cache.'),
    ('base.runtime.annotation.search', annotation_search, obj({'collection': {'enum': ['capabilities', 'lists']}}), response(array(CONFIG)), False, 'system.tech_config', 'Reads bounded documentation notes and status annotations for one named collection.'),
    ('base.runtime.capability_note.set', set_capability_note, obj({'id': {**ID, 'pattern': '^[a-z_]+$'}, 'value': TEXT}, ('id', 'value')), OK, True, 'system.tech_config', 'Saves one capability documentation note without changing governance decisions.'),
    ('base.runtime.capability_status.set', set_capability_status, obj({'id': {**ID, 'pattern': '^[a-z_]+$'}, 'value': {'enum': ['active', 'partial', 'planned']}}, ('id', 'value')), OK, True, 'system.tech_config', 'Saves one documentation status annotation without changing Capability lifecycle or approvals.'),
    ('base.runtime.list_note.set', set_list_note, obj({'id': {**ID, 'pattern': '^[a-z_]+$'}, 'value': TEXT}, ('id', 'value')), OK, True, 'system.tech_config', 'Saves one list documentation note.'),
    ('base.runtime.feishu_app_id.get', get_feishu_app_id, obj({}), response(CONFIG), False, 'system.tech_config', 'Reads the configured Feishu application identifier.'),
    ('base.runtime.feishu_app_id.set', set_feishu_app_id, obj({'value': ID}, ('value',)), OK, True, 'system.tech_config', 'Changes the Feishu application identifier and reloads settings.'),
    ('base.runtime.feishu_app_secret.set', set_feishu_app_secret, obj({'value': ID}, ('value',)), OK, True, 'system.tech_config', 'Replaces the Feishu application secret without returning it.'),
    ('base.runtime.log.search', search_logs, obj({'limit': {'type': 'integer', 'minimum': 1, 'maximum': 500}}), response(array(TEXT)), False, 'system.tech_config', 'Reads at most 500 bounded runtime diagnostic messages.'),
    ('base.file_store.minio_config.set', save_minio, obj({key: TEXT for key in ('endpoint', 'access_key', 'secret_key', 'bucket', 'public_url')}, ('endpoint', 'access_key')), OK, True, 'system.tech_config', 'Saves the explicit MinIO connection settings and reinitializes storage.'),
    ('base.file_store.ois_config.set', save_ois, obj({key: TEXT for key in ('identify', 'env', 'ois3_url', 'region', 'licloud_appid', 'idaas_url', 'idaas_client_id', 'idaas_client_secret', 'idaas_service_id', 'public_base_url')}, ('identify', 'ois3_url')), OK, True, 'system.tech_config', 'Saves the explicit OIS connection settings without returning credentials.'),
    ('base.file_store.minio_connection.test', test_minio, obj({}), CONNECTION, False, 'system.tech_config', 'Checks the configured MinIO connection and returns a bounded diagnostic outcome.'),
    ('base.file_store.ois_connection.test', test_ois, obj({}), CONNECTION, True, 'system.tech_config', 'Checks the configured OIS connection by writing the fixed connectivity probe object.'),
    ('base.feishu.calendar.day.get', calendar_day, obj({'date': {'type': 'string', 'pattern': '^\\d{4}-\\d{2}-\\d{2}$'}}), response(array(EVENT)), False, 'feishu.view', 'Reads at most 500 calendar events for the authenticated Feishu user on one day.'),
    ('base.feishu.calendar.event.get', event_get, obj({'event_id': ID}, ('event_id',)), obj({'success': {'const': True}, 'event': strings('event_id', 'summary', 'description')}, ('success', 'event')), False, 'feishu.view', 'Reads the editable title and description of one event visible to the authenticated Feishu user.'),
    ('base.feishu.calendar.event.update', event_update, obj({'event_id': ID, 'changes': {**obj({'summary': TEXT, 'description': TEXT}), 'minProperties': 1}}, ('event_id', 'changes')), OK, True, 'feishu.view', 'Changes one Feishu event title or description under the user delegated organizer permission.'),
    ('base.feishu.calendar.rsvp.set', event_rsvp, obj({'event_id': ID, 'rsvp_status': {'enum': ['accept', 'tentative', 'decline']}}, ('event_id', 'rsvp_status')), OK, True, 'feishu.view', 'Sets the authenticated user RSVP for one Feishu event.'),
    ('base.feishu.user.search', user_search, SEARCH, response(array(USER, 50)), False, 'feishu.view', 'Finds bounded Feishu contacts available to the authenticated user.'),
    ('base.feishu.chat.search', chat_search, SEARCH, response(array(CHAT, 50)), False, 'feishu.view', 'Finds bounded matching Feishu chats available to the authenticated user.'),
    ('base.feishu.document.search', document_search, SEARCH, response(array(DOCUMENT, 50)), False, 'feishu.view', 'Finds bounded matching Feishu documents available to the authenticated user.'),
    ('base.feishu.event.search', event_search, SEARCH, response(array(SEARCH_EVENT, 50)), False, 'feishu.view', 'Finds bounded matching Feishu calendar events available to the authenticated user.'),
    ('base.feishu.meeting.search', meeting_search, SEARCH, response(array(MEETING, 50)), False, 'feishu.view', 'Finds bounded matching Feishu meeting records available to the authenticated user.'),
    ('base.feishu.organization_user.search', organization_user_search, obj({'query': TEXT}, ('query',)), response(array(USER, 15)), False, 'system.user.manage', 'Finds up to 15 Feishu users and identifies their existing Base registrations.'),
    ('base.feishu.list_share.send', list_share_send, obj({'chat_id': ID, 'list_name': ID, 'share_url': {**TEXT, 'pattern': '^https://[^\\s]+$'}}, ('chat_id', 'list_name', 'share_url')), OK, True, 'feishu.view', 'Sends one explicitly confirmed list link to the selected Feishu chat.'),
]


def register_desktop_capabilities(registry):
    from .desktop_artifacts import DEFINITIONS as ARTIFACT_DEFINITIONS
    from .desktop_templates import DEFINITIONS as TEMPLATE_DEFINITIONS
    for capability_id, service, input_schema, output_schema, write, permission, effect in (*DEFINITIONS,*ARTIFACT_DEFINITIONS,*TEMPLATE_DEFINITIONS):
        request_validator = Draft202012Validator(input_schema)
        output_validator = Draft202012Validator(output_schema)

        @wraps(service)
        def handler(payload, context, _service=service, _request=request_validator, _output=output_validator, _artifact=capability_id.startswith('base.artifact.')):
            if not _request.is_valid(payload):
                raise CapabilityBusinessError('invalid_input', 'The request does not match this action.')
            try:
                actor = _actor(context)
                result = _service(payload, context if _artifact else actor)
            except HTTPException as error:
                raise CapabilityBusinessError({400: 'invalid_input', 403: 'permission_denied', 404: 'resource_not_found'}.get(error.status_code, 'dependency_failed'), 'The Base operation was rejected.') from error
            if not _output.is_valid(result):
                raise CapabilityBusinessError('provider_error', 'The Base result does not match the public contract.')
            return result

        spec = CapabilitySpec(id=capability_id, version=1, owner='base', description=effect,
            use_when=effect, do_not_use_when='The requested effect belongs to another named action.',
            risk='write' if write else 'read', confirmation='admin' if write and permission == 'system.tech_config' else 'user' if write else 'none',
            idempotent=True, permissions=(permission,) if permission else (), plugin_callable=False,
            input_schema=input_schema, output_schema=output_schema, tags=('base', 'desktop', 'closed'))
        descriptor = descriptor_from_provider_spec(spec).model_copy(update={
            'exposure': ExposurePolicy(web=True, api=True, plugin=False, agent=False, mcp=False),
            'exposure_policy_source': 'provider_explicit', 'authorization_policy': 'base.desktop:authenticated_owner',
            'delegation_policy': 'none', 'data_classification': 'restricted' if permission == 'system.tech_config' else 'confidential',
            'business_effect': effect, 'side_effects': effect, 'idempotency_policy': 'required' if write else 'none',
            'consistency_policy': 'external' if write else 'strong', 'transaction_policy': {'mode': 'provider', 'boundary': 'owning_domain'},
            'evidence_policy': 'optional', 'business_acceptance_criteria': (effect, 'The real owner service enforces the authenticated user scope and emits only the closed public model.'),
            'business_invariants': (BusinessInvariantContract(rule_id=capability_id + '.owner_bound', version=1,
                statement='Identity and current authorization come from the Base user and grant stores; callers cannot supply either.',
                applies_when='this desktop action is invoked', enforcement_ref='backend/base/desktop_actions.py:_actor',
                error_code='permission_denied', test_refs=('backend/tests/test_desktop_round5_base.py',)),),
            'no_business_invariant_reason': None,
        })
        registry.register(spec, handler, descriptor=descriptor)
