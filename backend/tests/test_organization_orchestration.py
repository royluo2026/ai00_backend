from types import SimpleNamespace
import pytest
from jsonschema import validate, ValidationError
from backend.tests.test_orchestration_repository import RecordingCursor, connection_factory, owned_version
from plugins.agent.agent_backend.orchestration.repository import OrchestrationRepository, ResourceNotAccessible, RevisionConflict
from plugins.agent.agent_backend.orchestration.models import GraphDraft
from plugins.agent.agent_backend.orchestration.provider import make_handler
from plugins.agent.agent_backend.capabilities.contracts import INPUT_SCHEMAS
from backend.capability_v2.provider_contracts import CapabilityBusinessError

PREFIX = 'agent.orchestration.organization.'

def test_oceanbase_scope_migration_and_commented_multi_column_normalization():
    from pathlib import Path
    from backend.capability_v2.domain_manifest import load_domain_manifests
    from backend.capability_v2.domain_migrations import discover_domain_migrations
    from backend.db.versioned_migrations import split_sql
    root = Path(__file__).resolve().parents[2]
    manifest = load_domain_manifests(root / 'backend/capability_v2/official_domains.json').require('agent')
    migrations = discover_domain_migrations(root, manifest)
    evidence = next(item for item in migrations if item.migration_id == '0011')
    assert all(statement.upper().count('ADD COLUMN') <= 1 for statement in split_sql(evidence.sql))
    assert any(item.migration_id == '0012' for item in migrations)

def test_organization_contract_rejects_client_scope_and_keeps_project_contract():
    schema = INPUT_SCHEMAS[PREFIX + 'panorama.read']
    validate({}, schema)
    for payload in ({'project_gid':'p'}, {'tenant_gid':'other'}):
        with pytest.raises(ValidationError): validate(payload, schema)
    with pytest.raises(ValidationError):
        validate({}, INPUT_SCHEMAS['agent.orchestration.panorama.read'])

def test_organization_list_is_shared_and_root_scoped():
    cursor = RecordingCursor()
    repository = OrchestrationRepository(connection_factory(cursor))
    assert repository.get_organization_panorama('tenant-1') is None
    sql, params = cursor.executions[0]
    assert "scope_kind='organization'" in sql
    assert 'owner_user_gid=%s' not in sql
    assert params == ('tenant-1',)

def test_organization_graph_requires_organization_root_and_null_project_children():
    cursor = RecordingCursor({'FROM workmanship_agent_orch_versions v': owned_version()})
    repository = OrchestrationRepository(connection_factory(cursor))
    graph = repository.get_graph('v1', actor_gid='other-member', tenant_gid='tenant-1', project_gid=None, organization=True)
    assert graph.nodes == []
    sql, params = cursor.executions[0]
    assert "p.scope_kind='organization'" in sql
    assert 'p.owner_user_gid=%s' not in sql
    assert params == ('v1', 'tenant-1', 'tenant-1')
    assert all('project_gid<=>%s' in sql for sql, _ in cursor.executions[1:])
    with pytest.raises(ResourceNotAccessible):
        repository.get_graph('v1', actor_gid='user', tenant_gid='tenant-1', project_gid=None)

def test_organization_save_checks_revision_before_replacing_children():
    cursor = RecordingCursor({'FROM workmanship_agent_orch_versions v': owned_version()})
    repo = OrchestrationRepository(connection_factory(cursor))
    assert repo.save_graph('v1', GraphDraft(nodes=[], edges=[]), expected_revision=7, actor_gid='editor', tenant_gid='tenant-1', organization=True) == 8
    assert "scope_kind='organization'" in cursor.executions[0][0]
    assert 'FOR UPDATE' in cursor.executions[0][0]
    with pytest.raises(RevisionConflict):
        repo.save_graph('v1', GraphDraft(nodes=[], edges=[]), expected_revision=6, actor_gid='editor', tenant_gid='tenant-1', organization=True)

def test_provider_uses_server_tenant_and_refuses_personal_identity():
    class Repo:
        def get_organization_panorama(self, tenant_gid): return {'tenant':tenant_gid}
    handler = make_handler(PREFIX+'panorama.read', repository=Repo(), resolver=None)
    context = SimpleNamespace(user_gid='u', effective_identity=SimpleNamespace(tenant=SimpleNamespace(tenant_id='team-1', membership='member')))
    assert handler({}, context) == {'panorama':{'tenant':'team-1'}, 'can_edit':False,'can_publish':False}
    context.permissions=('agent.read','agent.write')
    assert handler({},context)['can_edit'] is True
    context.effective_identity.tenant.tenant_id = 'user:u'
    with pytest.raises(CapabilityBusinessError) as denied: handler({}, context)
    assert denied.value.code == 'permission_denied'

def test_provider_returns_actionable_revision_conflict():
    class Repo:
        def save_graph(self, *args, **kwargs): raise RevisionConflict('stale draft')
    handler=make_handler(PREFIX+'graph.save',repository=Repo(),resolver=None)
    context=SimpleNamespace(user_gid='u',effective_identity=SimpleNamespace(tenant=SimpleNamespace(tenant_id='team-1')))
    with pytest.raises(CapabilityBusinessError) as conflict:
        handler({'version_gid':'v','expected_revision':1,'graph':{'nodes':[],'edges':[]}},context)
    assert conflict.value.code=='version_conflict'


def test_only_server_authenticated_super_admin_may_publish_org_panorama():
    class Repo:
        def get_organization_panorama(self, tenant_gid):return None
    context=SimpleNamespace(user_gid='u',permissions=('agent.read','agent.write'),active_roles=('team_admin',),effective_identity=SimpleNamespace(tenant=SimpleNamespace(tenant_id='team-1')))
    handler=make_handler(PREFIX+'version.publish',repository=Repo(),resolver=None)
    with pytest.raises(CapabilityBusinessError) as denied:handler({'version_gid':'v','expected_revision':1},context)
    assert denied.value.code=='permission_denied'
    read=make_handler(PREFIX+'panorama.read',repository=Repo(),resolver=None)
    assert read({},context)['can_edit'] and not read({},context)['can_publish']
    context.active_roles=('super_admin',)
    assert read({},context)['can_publish'] is True
