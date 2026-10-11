"""Project-manager writes with locked project ownership; historical versions stay frozen."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json

from backend.capability_v2.contracts import ResourceSelector, LifecycleStatus, BusinessInvariantContract, DomainErrorContract, CapabilityDescriptorV2
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.identity import get_active_identity_profile
from backend.platform_sdk.project_access import can_edit_project_bop
from backend.platform_sdk.craft_project_scope import entry_project_gid
from backend.platform_sdk.knowledge import readable_entry_scope
from backend.platform_sdk.artifacts import require_artifact
from ..application.service import ProjectManagementApplication
from ..data.connection import get_project_management_conn
from ..infrastructure.repository import ProjectManagementRepository, _ApprovalRejectionTransaction
from .provider import descriptor_for

VERSIONS = tuple((f'project.{kind}.change.apply.atomic.{kind}s_{action}', 2, 3)
                 for kind in ('task', 'issue') for action in ('create', 'update')) + (
    ('project.task_template.change.apply.atomic.task_templates_instantiate', 1, 2),
    ('project.approval.order.reject', 1, 2),
)


def deny(message):
    raise CapabilityBusinessError('permission_denied', message)


def validate_scope(repo, arguments, context, kind, action):
    actor, tenant = str(context.user_gid or ''), str(context.team_gid or '')
    project = str(arguments.get('project_gid') or '')
    if not actor or not tenant or not project:
        deny('Authenticated actor, tenant and project are required.')
    profile = get_active_identity_profile(actor)
    if not profile or str(profile.get('gid') or '') != actor or str(profile.get('team_id') or '') != tenant:
        deny('The active actor does not belong to this tenant.')
    if not can_edit_project_bop(actor, project, None, ()):
        deny('A current project manager responsibility is required.')
    row = repo.fetch_one('SELECT gid,team_id FROM workmanship_proj_projects WHERE gid=%s FOR UPDATE', (project,))
    if not row or str(row.get('team_id') or '') != tenant:
        deny('The project does not belong to this tenant.')
    target = {}
    if action == 'update':
        target = repo.fetch_one(f'SELECT * FROM workmanship_proj_{kind}s WHERE gid=%s FOR UPDATE', (arguments.get('gid'),))
        if not target or str(target.get('project_gid') or '') != project or str(target.get('owner_user_gid') or '') != actor:
            deny('The write target is outside the actor-owned project scope.')
        followers = repo.fetch_all('SELECT user_gid FROM workmanship_work_follows WHERE item_type=%s AND item_gid=%s FOR UPDATE', (kind, arguments['gid']))
        if any(str(item.get('user_gid') or '') != actor for item in followers):
            deny('This target has external notification recipients.')
    values = {**target, **arguments.get('updates', arguments)}
    if values.get('project_gid', project) != project:
        deny('Changing the project is not permitted.')
    for field in ('owner_user_gid', 'owner_gid'):
        if values.get(field) not in (None, '', actor):
            deny('The owner must be the authenticated actor.')
    if values.get('share_scope') not in (None, '', 'local', 'personal', 'project'):
        deny('Only personal or project sharing is permitted.')
    external_fields = ('assignee_team_gid', 'feishu_assignee_open_id', 'feishu_assignee_name',
                       'feishu_group_chat_id', 'feishu_group_name', 'feishu_groups', 'feishu_docs',
                       'meeting_doc_link', 'source_ref', 'tracking_refs', 'progress_logs')
    if any(values.get(field) for field in external_fields):
        deny('External assignment, notification and untyped references are not supported.')
    if values.get('bop_entry_gid') and entry_project_gid(values['bop_entry_gid'], context) != project:
        deny('The Craft entry is outside the project.')
    if values.get('related_knowledge_gid'):
        reference = values['related_knowledge_gid']
        knowledge = readable_entry_scope(reference, context)
        if not knowledge or str(knowledge.get('gid') or '') != reference:
            deny('The Knowledge entry is unavailable.')
        source_project = str(knowledge.get('source_project_gid') or '')
        if source_project:
            if source_project != project: deny('The Knowledge entry belongs to another project.')
        elif knowledge.get('share_scope') != 'global' and str(knowledge.get('creator_gid') or '') != actor:
            deny('Unassigned Knowledge entries must be public or actor-owned.')
    for field, table in (('list_gid', 'workmanship_work_lists'),
                         ('parent_task_gid', 'workmanship_proj_tasks'),
                         ('related_task_gid', 'workmanship_proj_tasks'),
                         ('approval_order_gid', 'workmanship_proj_approval_orders')):
        if values.get(field):
            related = repo.fetch_one(f'SELECT project_gid FROM {table} WHERE gid=%s FOR UPDATE', (values[field],))
            if not related or str(related.get('project_gid') or '') != project:
                deny(f'{field} is outside the project.')
    for artifact in values.get('attachments') or []:
        require_artifact(artifact['artifact_ref'], context)
    return project


class _VersionedCursor:
    """Keep the existing rejection transaction but bind its replay namespace to @2."""
    def __init__(self, cursor): self.cursor = cursor
    def __enter__(self): self.cursor.__enter__(); return self
    def __exit__(self, *args): return self.cursor.__exit__(*args)
    def __getattr__(self, name): return getattr(self.cursor, name)
    def execute(self, sql, params=()):
        return self.cursor.execute(sql.replace('project.approval.order.reject@1', 'project.approval.order.reject@2'), params)


class _RejectionConnection:
    def __init__(self, connection): self.connection = connection
    def cursor(self): return _VersionedCursor(self.connection.cursor())


class ScopedRepository(ProjectManagementRepository):
    def __init__(self, connection): self.connection = connection
    def fetch_all(self, sql, params=()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params); return [dict(row) for row in cursor.fetchall()]
    def fetch_one(self, sql, params=()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params); row = cursor.fetchone(); return dict(row) if row else None
    def execute(self, sql, params=()):
        with self.connection.cursor() as cursor: return int(cursor.execute(sql, params))
    @contextmanager
    def transaction(self):
        yield _ApprovalRejectionTransaction(_RejectionConnection(self.connection))
    def create_tasks_from_template(self, tasks):
        for task in tasks:
            self.execute('INSERT INTO workmanship_proj_tasks (gid,title,description,owner_user_gid,project_gid,priority,share_scope,due_date,template_item_gid,template_source_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         tuple(task.get(key) for key in ('gid','title','description','owner_user_gid','project_gid','priority')) + ('project',) + tuple(task.get(key) for key in ('due_date','template_item_gid','template_source_version')))


def scoped_handler(capability, version, kind, action):
    def invoke(payload, context):
        arguments = deepcopy(payload.get('arguments', payload))
        with get_project_management_conn() as connection:
            repo = ScopedRepository(connection)
            try:
                project = validate_scope(repo, arguments, context, kind, action)
                if kind == 'template':
                    template = repo.fetch_one("SELECT gid FROM workmanship_work_task_templates WHERE gid=%s AND scope='system' AND is_active=1 FOR UPDATE", (arguments.get('gid'),))
                    if not template: deny('Only active public templates may be instantiated.')
                    arguments['owner_user_gid'] = context.user_gid
                    if arguments.get('assignee_map'):
                        deny('Independent template assignee persistence is not supported.')
                if kind == 'approval':
                    order = repo.fetch_one('SELECT project_gid,applicant_gid,reviewer_gid,order_type FROM workmanship_proj_approval_orders WHERE gid=%s FOR UPDATE', (arguments.get('order_gid'),))
                    if not order or str(order.get('project_gid') or '') != project or order.get('order_type') == 'scope_upgrade' or any(str(order.get(key) or '') != context.user_gid for key in ('applicant_gid','reviewer_gid')):
                        deny('The approval project or participants are outside this scope.')
                key = str(getattr(context, 'idempotency_key', '') or '')
                if not key or len(key) > 255:
                    raise CapabilityBusinessError('invalid_input', 'A bounded idempotency key is required.')
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                identity = (context.user_gid, context.team_gid, f'{capability}@{version}', key)
                repo.execute('INSERT INTO workmanship_proj_desktop_operations (actor_gid,team_gid,capability_id,idempotency_key,payload_hash) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE actor_gid=VALUES(actor_gid)', (*identity, digest))
                prior = repo.fetch_one('SELECT payload_hash,result_text FROM workmanship_proj_desktop_operations WHERE actor_gid=%s AND team_gid=%s AND capability_id=%s AND idempotency_key=%s FOR UPDATE', identity)
                if not prior or prior['payload_hash'] != digest:
                    raise CapabilityBusinessError('idempotency_conflict', 'This key belongs to a different scoped request.')
                if prior.get('result_text'):
                    result = json.loads(prior['result_text'])
                else:
                    app = ProjectManagementApplication(repo)
                    if kind == 'approval':
                        arguments.pop('project_gid')
                        result = app.invoke(capability, arguments, context)
                    else:
                        source = 'project.task_template.change.apply' if kind == 'template' else f'project.{kind}.change.apply'
                        operation = 'task_templates.instantiate' if kind == 'template' else f'{kind}s.{action}'
                        # project_gid is an authorization selector for updates, not a mutable field.
                        if action == 'update': arguments.pop('project_gid')
                        result = {'data': app.invoke(source, {'operation': operation, 'arguments': arguments}, context)}
                    repo.execute('UPDATE workmanship_proj_desktop_operations SET result_text=%s,completed_at=CURRENT_TIMESTAMP(6) WHERE actor_gid=%s AND team_gid=%s AND capability_id=%s AND idempotency_key=%s', (json.dumps(result, ensure_ascii=False, separators=(',', ':')), *identity))
                connection.commit()
                return result
            except BaseException:
                connection.rollback(); raise
    return invoke


def register_scoped_writes(registry):
    for capability, old_version, version in VERSIONS:
        original = registry.get(capability, old_version)
        schema = deepcopy(original.spec.input_schema)
        target = schema['properties']['arguments'] if 'arguments' in schema['properties'] else schema
        target['properties']['project_gid'] = {'type':'string', 'minLength':1, 'maxLength':128}
        knowledge_field = target['properties'].get('related_knowledge_gid') or target['properties'].get('updates', {}).get('properties', {}).get('related_knowledge_gid')
        if knowledge_field is not None:
            knowledge_field['description'] = 'Knowledge entry GID (workmanship_know_entries); legacy Knowledge Hub item GIDs are not accepted.'
        target['required'] = list(dict.fromkeys([*target.get('required', []), 'project_gid']))
        kind = 'template' if '.task_template.' in capability else 'approval' if '.approval.' in capability else 'task' if '.task.' in capability else 'issue'
        action = 'reject' if kind == 'approval' else 'instantiate' if kind == 'template' else capability.rsplit('_', 1)[-1]
        if kind == 'template':
            target['properties']['assignee_map'] = {'type':'object', 'properties':{}, 'additionalProperties':False,
                                                   'description':'Independent assignee persistence is unsupported; instantiate actor-owned tasks with an empty map.'}
        spec = original.spec.model_copy(update={'version':version, 'input_schema':schema, 'permissions':('project.manage_assigned',), 'idempotent':True})
        source_ref = 'plugins.project_management.project_management_backend.capabilities.scoped_writes'
        test_ref = 'backend/tests/test_project_scoped_writes.py'
        effect = ('Instantiate an active public task template as tasks owned by the authenticated manager in the selected project.' if kind == 'template'
                  else 'Reject an in-review approval order and atomically record its revision, audit and participant notification.' if kind == 'approval'
                  else f'{"Create an actor-owned" if action == "create" else "Update an actor-owned"} {kind} in the selected managed project and return the committed outcome.')
        base_descriptor = descriptor_for(spec)
        errors = {item.code:item for item in base_descriptor.domain_errors}
        for code, meaning in (
            ('invalid_input','The request has missing or unsupported input.'),
            ('idempotency_conflict','The scoped request key was previously used with different input.'),
            ('idempotency_required','A write key is required.'),
            ('confirmation_required','The approval rejection lacks confirmation.'),
            ('invalid_state','The approval order cannot transition from its current state.'),
            ('not_found','The target record or assigned reviewer is unavailable.'),
            ('invalid_result','The stored rejection result is invalid.'),
            ('forbidden','The existing attachment owner check refused the change.'),
        ):
            errors[code] = DomainErrorContract(code=code,meaning=meaning,retryable=False)
        data = base_descriptor.model_dump()
        data.update({
            'lifecycle_status':LifecycleStatus.EXPERIMENTAL,
            'resource_selectors':(ResourceSelector(resource_type='project', payload_path='arguments.project_gid' if target is not schema else 'project_gid', required=True),),
            'business_acceptance_criteria': (*original.descriptor.business_acceptance_criteria, 'The current authenticated project manager commits only actor-owned project records with checked typed references in one domain transaction.'),
            'business_effect':effect,
            'business_invariants':(BusinessInvariantContract(
                rule_id='project.scoped_write.same_project',version=1,
                statement='Every changed record and typed project reference belongs to the selected project, with no external recipients or wider sharing.',
                applies_when='A project manager applies a scoped write.',
                enforcement_ref=source_ref+':validate_scope',error_code='permission_denied',
                test_refs=(test_ref+'::test_update_target_and_typed_parent_cannot_cross_project',test_ref+'::test_knowledge_entry_scope_and_public_rules'),
            ),),
            'no_business_invariant_reason':None,
            'provider_ref':source_ref+':scoped_handler',
            'test_refs':({'path':test_ref},),
            'consumer_refs':(),
            'no_consumer_reason':'Demo consumer migration is pending; existing consumers retain their explicit historical versions.',
            'domain_errors':tuple(errors.values()),
            'error_schema':(),
            'operation_policy': original.descriptor.operation_policy,
            'replay_data_policy': original.descriptor.replay_data_policy,
            'concurrency_policy': original.descriptor.concurrency_policy,
            'expected_version_payload_path': original.descriptor.expected_version_payload_path,
        })
        if kind == 'template':
            data['do_not_use_when']='Independent task assignees or Feishu responsibility assignment must be persisted; this version only instantiates actor-owned tasks with an empty assignee map.'
        descriptor = CapabilityDescriptorV2.model_validate(data)
        registry.register(spec, scoped_handler(capability, version, kind, action), descriptor=descriptor)
