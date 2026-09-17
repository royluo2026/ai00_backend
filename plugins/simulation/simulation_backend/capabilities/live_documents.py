"""Candidate user-owned binding of attested VisMockup documents to environments."""
from datetime import UTC, datetime, timedelta
import jsonschema

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityOutput, CapabilityRisk, CapabilitySpec, EvidenceRef
from backend.contracts.connector_execution_plan_v1 import canonical_hash
from ..data.connector_repository import ConnectorRepositoryError, _utc
from ..data.workspace_repository import WorkspaceRepository, WorkspaceRepositoryError

KEY = {'type': 'string', 'minLength': 1, 'maxLength': 191}
GID = {'type': 'string', 'pattern': '^[1-9][0-9]*$'}
HASH = {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}
def obj(properties, required=None):
    return dict(type='object', properties=properties, required=list(properties if required is None else required), additionalProperties=False)

ADOPT_INPUT_V1 = obj(dict(identity_operation_id=KEY, name={'type':'string','minLength':1,'maxLength':200},
    idempotency_key=KEY))
ADOPT_INPUT = obj(dict(identity_operation_id=KEY, name={'type':'string','minLength':1,'maxLength':200},
    document_display_name={'type':'string','minLength':1,'maxLength':255}, idempotency_key=KEY))
BINDING_INPUT = {**obj(dict(identity_operation_id=KEY, workspace_gid=GID), []),
    'oneOf': [{'required':['identity_operation_id']}, {'required':['workspace_gid']} ]}
REBIND_INPUT = obj(dict(workspace_gid=GID, identity_operation_id=KEY,
    expected_document_session=HASH, expected_workspace_row_version={'type':'integer','minimum':1},
    idempotency_key=KEY))
ONLINE_BIND_INPUT = obj(dict(workspace_gid=GID, document_gid=GID,
    launch_operation_id=KEY, identity_operation_id=KEY,
    expected_workspace_row_version={'type':'integer','minimum':1}, idempotency_key=KEY))
ADOPT_OUTPUT_V1 = obj(dict(workspace_gid=GID, version_gid=GID,
    state={'type':'string','enum':['importing']}, created={'type':'boolean'}))
ADOPT_OUTPUT = obj(dict(workspace_gid=GID, version_gid=GID, model_document_gid=GID,
    state={'type':'string','enum':['importing']}, created={'type':'boolean'}))
BINDING_OUTPUT = obj(dict(state={'type':'string','enum':['unbound','unavailable','importing','bound']},
    workspace_gid={'type':['string','null']}, version_gid={'type':['string','null']},
    connector_device_id={'type':['string','null']}, document_session={'type':['string','null']}))
REBIND_OUTPUT = obj(dict(workspace_gid=GID, document_gid=GID,
    state={'type':'string','enum':['importing','bound']}, connector_device_id=KEY,
    document_session=HASH, workspace_row_version={'type':'integer','minimum':1},
    cache_revision_hash=HASH))
ONLINE_BIND_OUTPUT = REBIND_OUTPUT
INVENTORY_APPLY_INPUT = obj(dict(workspace_gid=GID, inventory_operation_id=KEY, idempotency_key=KEY))
INVENTORY_APPLY_OUTPUT = obj(dict(workspace_gid=GID,
    imported_hierarchy_count={'type':'integer','minimum':0}, next_index={'type':['integer','null'],'minimum':0},
    total_hierarchies={'type':'integer','minimum':0}, complete={'type':'boolean'},
    workspace_row_version={'type':'integer','minimum':1},
    cache_revision_hash={'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}))


class LiveDocumentProvider:
    def __init__(self, connectors, workspaces=None, *, clock=lambda: datetime.now(UTC)):
        self.connectors, self.workspaces, self.clock = connectors, workspaces or WorkspaceRepository(), clock

    @staticmethod
    def _scope(payload, context, schema):
        if context.source != 'web' or not context.user_gid or not context.team_gid:
            raise CapabilityBusinessError('live_document_owner_required', 'Authenticated web owner required.')
        try: jsonschema.validate(payload, schema)
        except jsonschema.ValidationError as exc:
            raise CapabilityBusinessError('live_document_input_invalid', 'Invalid live document request.') from exc
        return dict(tenant_gid=context.team_gid, actor_gid=context.user_gid)

    @staticmethod
    def _output(data):
        return CapabilityOutput(data=data, evidence=(EvidenceRef(kind='simulation.live_document.binding',
            reference='simulation-live-document-binding', digest=canonical_hash(data)),))

    def _adopt(self, payload, context, schema, document_display_name):
        scope = self._scope(payload, context, schema)
        try:
            identity = self.connectors.verified_document_identity(payload['identity_operation_id'],
                actor_id=context.user_gid, tenant_id=context.team_gid, now=self.clock())
            result = self.workspaces.adopt_live_document(**scope, **identity, name=payload['name'],
                document_display_name=document_display_name, idempotency_key=payload['idempotency_key'])
        except (ConnectorRepositoryError, WorkspaceRepositoryError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return self._output(result)

    def adopt_v1(self, payload, context):
        return self._adopt(payload, context, ADOPT_INPUT_V1, None)

    def adopt(self, payload, context):
        return self._adopt(payload, context, ADOPT_INPUT, payload.get('document_display_name'))

    def binding(self, payload, context):
        scope = self._scope(payload, context, BINDING_INPUT)
        empty = dict(state='unbound', workspace_gid=None, version_gid=None, connector_device_id=None, document_session=None)
        try:
            if 'identity_operation_id' in payload:
                identity = self.connectors.verified_document_identity(payload['identity_operation_id'],
                    actor_id=context.user_gid, tenant_id=context.team_gid, now=self.clock())
                binding = self.workspaces.find_live_document_binding(**scope, **identity)
                result = {**empty, **identity, **(binding or {})}
            else:
                binding = self.workspaces.live_document_binding_for_workspace(**scope, workspace_gid=payload['workspace_gid'])
                if not binding: return self._output(empty)
                runtime = self.connectors.bound_runtime_for_user(context.user_gid, context.team_gid)
                now = self.clock()
                if (not runtime or runtime['device_id'] != binding['connector_device_id']
                    or runtime['owner_user_gid'] != context.user_gid or runtime['tenant_gid'] != context.team_gid
                    or runtime['runtime_type'] != 'electron' or runtime['status'] != 'active'
                    or runtime['protocol'] != 'ai00.connector.execution-plan.v2' or runtime['runtime_generation'] < 1
                    or not runtime['current_runtime_instance_id'] or not runtime['session_token_hash']
                    or _utc(runtime['session_expires_at']) <= now
                    or not now - timedelta(seconds=120) <= _utc(runtime['heartbeat_at']) <= now):
                    return self._output({**empty, 'state':'unavailable'})
                result = dict(binding)
            if result['state'] not in {'unbound','importing','bound'}:
                result = {**empty, 'state':'unavailable'}
        except (ConnectorRepositoryError, WorkspaceRepositoryError, KeyError, TypeError, AttributeError, ValueError):
            result = {**empty, 'state':'unavailable'}
        return self._output(result)

    def rebind(self, payload, context):
        scope = self._scope(payload, context, REBIND_INPUT)
        try:
            identity = self.connectors.verified_document_identity(
                payload['identity_operation_id'], actor_id=context.user_gid,
                tenant_id=context.team_gid, now=self.clock())
            result = self.workspaces.rebind_live_document(
                **scope, **identity, workspace_gid=payload['workspace_gid'],
                expected_document_session=payload['expected_document_session'],
                expected_workspace_row_version=payload['expected_workspace_row_version'],
                idempotency_key=payload['idempotency_key'])
        except (ConnectorRepositoryError, WorkspaceRepositoryError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return self._output(result)

    def bind_online(self, payload, context):
        scope = self._scope(payload, context, ONLINE_BIND_INPUT)
        try:
            launch = self.connectors.verified_teamcenter_launch(
                payload['launch_operation_id'], actor_id=context.user_gid,
                tenant_id=context.team_gid, now=self.clock())
            identity = self.connectors.verified_document_identity(
                payload['identity_operation_id'], actor_id=context.user_gid,
                tenant_id=context.team_gid, now=self.clock())
            if launch['connector_device_id'] != identity['connector_device_id']:
                raise WorkspaceRepositoryError('launch_document_device_mismatch')
            result = self.workspaces.bind_online_live_document(
                **scope, **identity, workspace_gid=payload['workspace_gid'],
                document_gid=payload['document_gid'],
                source_identity_hash=launch['source_identity_hash'],
                expected_workspace_row_version=payload['expected_workspace_row_version'],
                idempotency_key=payload['idempotency_key'])
        except (ConnectorRepositoryError, WorkspaceRepositoryError, KeyError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return self._output(result)

    def apply_inventory(self, payload, context):
        scope = self._scope(payload, context, INVENTORY_APPLY_INPUT)
        try:
            page = self.connectors.verified_hierarchy_inventory(payload['inventory_operation_id'],
                actor_id=context.user_gid, tenant_id=context.team_gid, now=self.clock())
            connector_device_id = page.pop('connector_device_id')
            document_session = page['document_session']
            result = self.workspaces.apply_live_hierarchy_inventory(**scope,
                workspace_gid=payload['workspace_gid'], connector_device_id=connector_device_id,
                document_session=document_session, inventory_operation_id=payload['inventory_operation_id'],
                page=page, idempotency_key=payload['idempotency_key'])
        except (ConnectorRepositoryError, WorkspaceRepositoryError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return self._output(result)


def register_live_document_capabilities(registry, control_plane):
    from .provider import register
    provider = LiveDocumentProvider(control_plane.repository, clock=control_plane.clock)
    for name, version, description, risk, input_schema, output_schema, handler in (
        ('adopt', 1, 'Create or reuse a private importing environment for one authenticated native document.', CapabilityRisk.WRITE, ADOPT_INPUT_V1, ADOPT_OUTPUT_V1, provider.adopt_v1),
        ('adopt', 2, 'Create or reuse an importing environment and register its primary live VisMockup document.', CapabilityRisk.WRITE, ADOPT_INPUT, ADOPT_OUTPUT, provider.adopt),
        ('binding.get', 1, 'Resolve the owner-scoped environment binding of a native document or selected environment.', CapabilityRisk.READ, BINDING_INPUT, BINDING_OUTPUT, provider.binding),
        ('rebind', 1, 'Explicitly bind the selected environment to a freshly attested current native document session.', CapabilityRisk.WRITE, REBIND_INPUT, REBIND_OUTPUT, provider.rebind),
        ('inventory.apply', 1, 'Persist one signed bounded alternate-hierarchy inventory page into its bound environment.', CapabilityRisk.WRITE, INVENTORY_APPLY_INPUT, INVENTORY_APPLY_OUTPUT, provider.apply_inventory),
    ):
        register(registry, CapabilitySpec(id='simulation.environment.live_document.'+name, owner='simulation', version=version,
            description=description, use_when='The owner links or selects an already-open native document.',
            do_not_use_when='Native identity is unavailable or another user owns the binding.', risk=risk,
            confirmation='user' if name == 'rebind' else 'none', permissions=('simulation.use',), input_schema=input_schema, output_schema=output_schema,
            tags=('simulation','live_document','experimental')), handler)
    register(registry, CapabilitySpec(
        id='simulation.environment.online_source.live_document.bind', owner='simulation', version=1,
        description='Bind a freshly launched Teamcenter online source document to its attested VisMockup session.',
        use_when='A user-confirmed Teamcenter launch has opened a new VisMockup document for an owned online-source model.',
        do_not_use_when='Either signed launch evidence or current native document identity is unavailable or mismatched.',
        risk=CapabilityRisk.WRITE, confirmation='user', permissions=('simulation.use',),
        input_schema=ONLINE_BIND_INPUT, output_schema=ONLINE_BIND_OUTPUT,
        tags=('simulation','teamcenter_online','live_document','experimental')),
        provider.bind_online)
