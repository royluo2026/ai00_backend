"""Base-owned marketplace administration through closed, atomic capabilities."""
from functools import partial

from jsonschema import Draft202012Validator

from backend.base import desktop_actions
from backend.base.plugin_marketplace import obj, TEXT, GRANTS, _metadata
from backend.capability_v2.contracts import ArtifactRef, BusinessInvariantContract, DomainErrorContract, ExposurePolicy
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec

PREFIX = 'base.plugin.marketplace.'
ID = {'type': 'string', 'minLength': 1, 'maxLength': 128}
DIGEST = {'type': 'string', 'pattern': '^sha256:[a-f0-9]{64}$'}
NOTE = {'type': 'string', 'minLength': 1, 'maxLength': 4000, 'pattern': r'\S'}
STATUS = {'enum': ['submitted', 'published', 'rejected', 'revoked']}
TARGET = {'plugin_id': ID, 'version': ID, 'release_sha256': DIGEST, 'note': NOTE}
RESULT = {'plugin_id': ID, 'version': ID, 'status': STATUS}
ROW = obj({**RESULT, 'name': TEXT, 'description': TEXT, 'publisher_id': TEXT,
           'release_sha256': DIGEST, 'requested_grants': GRANTS, 'review_note': TEXT,
           'submitted_by': TEXT, 'reviewed_by': TEXT, 'updated_at': TEXT})
CONTRACTS = {
    'submit': ('release.submit', 1, obj({'artifact_ref': ArtifactRef.model_json_schema()}), obj(RESULT)),
    'access': ('administration.access.get', 1, obj({}), obj({'can_admin': {'type': 'boolean'}})),
    'search': ('release.search', 1, obj({'status': STATUS, 'query': {'type': 'string', 'maxLength': 200},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200},
        'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1000000}}, []),
        obj({'items': {'type': 'array', 'maxItems': 200, 'items': ROW}, 'next_offset': {'type': ['integer', 'null'], 'minimum': 0}})),
    'review': ('release.review', 1, obj({**TARGET, 'approved': {'type': 'boolean'}}), obj(RESULT)),
    'revoke': ('release.revoke', 1, obj(TARGET), obj({**RESULT, 'affected_installations': {'type': 'integer', 'minimum': 0}})),
    'publisher': ('publisher.register', 2, obj({'publisher_id': ID, 'display_name': {'type': 'string', 'minLength': 1, 'maxLength': 255},
        'public_key_pem': {'type': 'string', 'minLength': 80, 'maxLength': 4096}}),
        obj({'publisher_id': ID, 'key_fingerprint': TEXT, 'status': {'const': 'active'}})),
}
DESCRIPTIONS = {
    'submit': 'Validates an owned signed plugin package and records its immutable version for super administrator review.',
    'access': 'Returns whether the current authenticated Base user can administer platform plugin releases.',
    'search': 'Returns a bounded platform release review queue with version digests and review history to a super administrator.',
    'review': 'Records a super administrator decision on one submitted plugin version; approval publishes a platform-signed release.',
    'revoke': 'Revokes one published plugin version and its active installations across tenants in one owner transaction.',
    'publisher': 'Registers an immutable publisher namespace and its Ed25519 public signing key.',
}


def _search(payload):
    from backend.db.connection import get_conn
    query = payload.get('query', '').strip().replace('!', '!!').replace('%', '!%').replace('_', '!_')
    limit, offset = payload.get('limit', 50), payload.get('offset', 0)
    sql = ('SELECT plugin_id,version,publisher_id,manifest,artifact_sha256,status,review_note,submitted_by,reviewed_by,updated_at '
           "FROM workmanship_plugin_releases WHERE (plugin_id LIKE %s ESCAPE '!' OR manifest LIKE %s ESCAPE '!')")
    params = ['%' + query + '%', '%' + query + '%']
    if payload.get('status'):
        sql += ' AND status=%s'
        params.append(payload['status'])
    sql += ' ORDER BY updated_at DESC,plugin_id,version LIMIT %s OFFSET %s'
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (*params, limit + 1, offset))
            rows = cur.fetchall()
    items = []
    for row in rows[:limit]:
        manifest = _metadata(row.get('manifest') or {}, dict)
        items.append({**{key: str(row.get(key) or '') for key in ('plugin_id', 'version', 'publisher_id', 'status', 'review_note', 'submitted_by', 'reviewed_by', 'updated_at')},
                      'name': str(manifest.get('name') or row['plugin_id'])[:4000],
                      'description': str(manifest.get('description') or '')[:4000],
                      'release_sha256': 'sha256:' + str(row.get('artifact_sha256') or ''),
                      'requested_grants': _metadata(manifest.get('permissions') or [], list)})
    return {'items': items, 'next_offset': offset + limit if len(rows) > limit else None}


def execute(action, payload, context):
    from backend.plugin_platform import service
    actor = desktop_actions._actor(context)
    if action != 'access':
        desktop_actions._super(actor)
    _, _, input_schema, output_schema = CONTRACTS[action]
    if not Draft202012Validator(input_schema).is_valid(payload):
        raise CapabilityBusinessError('invalid_input', 'Input does not match the closed administration contract.')
    try:
        if action == 'access':
            result = {'can_admin': 'super_admin' in {actor.get('system_role'), actor.get('org_role')}}
        elif action == 'search':
            result = _search(payload)
        elif action == 'publisher':
            result = service.register_publisher(payload['publisher_id'], payload['display_name'], payload['public_key_pem'], str(context.user_gid))
        elif action == 'submit':
            from backend.plugin_platform.package_upload import submit_package
            result = submit_package(payload['artifact_ref'], context)
        elif action == 'review':
            result = service.review_release(payload['plugin_id'], payload['version'], payload['approved'], payload['note'], str(context.user_gid), expected_sha256=payload['release_sha256'])
        else:
            result = service.revoke_release(payload['plugin_id'], payload['version'], payload['note'], str(context.user_gid), expected_sha256=payload['release_sha256'])
    except ValueError as exc:
        raise CapabilityBusinessError('marketplace_state_conflict', str(exc)) from exc
    if not Draft202012Validator(output_schema).is_valid(result):
        raise CapabilityBusinessError('marketplace_data_invalid', 'Stored marketplace metadata violates the administration contract.')
    return result


def register_marketplace_admin(registry):
    for action, (suffix, major, input_schema, output_schema) in CONTRACTS.items():
        read = action in ('access', 'search')
        spec = CapabilitySpec(owner='base', id=PREFIX + suffix, version=major,
            description=DESCRIPTIONS[action], risk='read' if read else 'destructive' if action == 'revoke' else 'write',
            confirmation='none' if read else 'admin', permissions=(), plugin_callable=False,
            input_schema=input_schema, output_schema=output_schema, tags=('base', 'plugin', 'administration'))
        descriptor = descriptor_from_provider_spec(spec).model_copy(update={
            'authorization_policy': 'base.v2:authenticated',
            'exposure': ExposurePolicy(web=True, api=True, plugin=False, agent=False, mcp=False),
            'exposure_policy_source': 'provider_explicit', 'agent_output_schema': None,
            # Existing owner services commit their own SQL transaction, like
            # Base desktop_actions. They do not enlist in Gateway's transaction.
            'delegation_policy': 'none', 'consistency_policy': 'strong' if read else 'external',
            'idempotency_policy': 'none' if read else 'required', 'data_classification': 'confidential',
            'timeout_seconds': 600 if action == 'submit' else 30,
            'domain_errors': tuple(DomainErrorContract(code=code, meaning=meaning) for code, meaning in (
                ('permission_denied', 'The current active Base actor lacks authority or has changed tenant.'),
                ('invalid_input', 'Input violates the closed administration contract.'),
                ('marketplace_state_conflict', 'Release state, digest, signature or publisher registration rejects this operation.'),
                ('marketplace_data_invalid', 'Stored metadata violates the bounded projection.'))),
            'domain_errors_complete': True,
            'business_invariants': (BusinessInvariantContract(rule_id='base.plugin.marketplace.super_admin', version=1,
                statement='Only a freshly resolved Base super administrator can read platform review data or administer releases and publishers.',
                applies_when='administration data or effects other than the caller access flag are requested',
                enforcement_ref='backend/base/plugin_marketplace_admin.py:execute', error_code='permission_denied',
                test_refs=('backend/tests/test_plugin_marketplace_admin.py::test_admin_boundary_rechecks_role_before_owner_write',)),),
            'business_acceptance_criteria': (DESCRIPTIONS[action], 'No caller-supplied actor, tenant or role grants authority.'),
        })
        descriptor = type(descriptor).model_validate(descriptor.model_dump())
        registry.register(spec, partial(execute, action), descriptor=descriptor)
