"""Candidate organization contracts through the real Registry/Gateway/authorizer."""
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationGrants
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import InvocationEnvelope
from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.identity import AuthenticatedPrincipal, authenticated_user_identity
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.provider_loader import hash_domain_artifact
from plugins.agent.agent_backend.capabilities import register_capabilities

PREFIX='agent.orchestration.organization.'

def gateway(permissions):
    calls=[]
    class Repository:
        def get_organization_panorama(self, tenant): calls.append(tenant); return None
        def get_organization_slice(self, version_gid, **kwargs):
            from plugins.agent.agent_backend.orchestration.models import GraphDraft
            calls.append(kwargs)
            return {'graph':GraphDraft(nodes=[],edges=[]).model_dump(mode='json'),'complete':False,'revision':7,'loaded_view_gids':[],'loaded_node_gids':[]}
    registry=CapabilityRegistry()
    register_capabilities(registry,canvas_runtime=None,orchestration_repository_factory=Repository)
    root=Path(__file__).resolve().parents[2]
    manifest=load_domain_manifests(root/'backend/capability_v2/official_domains.json').require('agent')
    artifact=manifest.artifact.model_copy(update={'artifact_hash':hash_domain_artifact(root,manifest.artifact_path)})
    registry.bind_provider_artifact('agent',artifact)
    release=build_release([item.descriptor for item in registry.snapshot() if item.spec.id.startswith(PREFIX)],[artifact])
    store=InMemoryCatalogStore();store.publish(release)
    policy=LegacyServerGatewayPolicy(lambda actor:{'gid':actor,'is_active':True},lambda identity,user:AuthorizationGrants(
        permissions=permissions,capability_scopes=('*',),resource_scopes=('*',),data_scopes=('confidential',),
        tenant_id=identity.tenant.tenant_id,policy_version='organization-test-policy'))
    service=CapabilityGatewayService(CatalogResolver(store,registry),policy).bind_release(release.release_id)
    def invoke(suffix,payload=None,actor='member-1',tenant='organization-1'):
        principal=AuthenticatedPrincipal(user_id=actor,authentication_method='test-jwt',authenticated_at=datetime.now(UTC))
        identity=authenticated_user_identity({'gid':actor,'team_id':tenant},principal)
        return asyncio.run(service.invoke(InvocationEnvelope(capability_id=PREFIX+suffix,major_version=1,
            catalog_release=release.release_id,payload=payload or {},identity=identity,request_id='request-1',trace_id='trace-1',
            idempotency_key='organization-test-key' if not suffix.endswith('read') else None)))
    return invoke,calls

def test_real_gateway_reads_server_organization_and_projects_edit_permission():
    invoke,calls=gateway(('agent.read',))
    result=invoke('panorama.read')
    assert result.ok and result.data=={'panorama':None,'can_edit':False}
    assert invoke('panorama.read',actor='member-2').ok
    assert calls==['organization-1','organization-1']
    editor,_=gateway(('agent.read','agent.write'))
    assert editor('panorama.read').data['can_edit'] is True

def test_gateway_denies_read_without_agent_permission():
    invoke,calls=gateway(())
    result=invoke('panorama.read')
    assert not result.ok and result.error.code=='permission_denied'
    assert calls==[]

def test_gateway_denies_write_before_repository_for_read_only_member():
    invoke,calls=gateway(('agent.read',))
    result=invoke('panorama.create',{'name':'Organization'})
    assert not result.ok and result.error.code=='permission_denied'
    assert calls==[]

def test_gateway_rejects_client_scope_and_personal_identity():
    invoke,calls=gateway(('agent.read',))
    assert not invoke('panorama.read',{'tenant_gid':'another-organization'}).ok
    assert calls==[]
    result=invoke('panorama.read',tenant='user:member-1')
    assert not result.ok and result.error.code=='permission_denied'
    assert calls==[]


def test_real_gateway_accepts_bounded_projection_and_preserves_server_scope():
    invoke,calls=gateway(('agent.read',))
    result=invoke('graph.read',{'version_gid':'v','projection':'directory','expected_revision':7})
    assert result.ok and result.data['complete'] is False
    assert calls[0]['tenant_gid']=='organization-1' and calls[0]['projection']=='directory'
    assert not invoke('graph.read',{'version_gid':'v','projection':'view','tenant_gid':'attacker'}).ok
