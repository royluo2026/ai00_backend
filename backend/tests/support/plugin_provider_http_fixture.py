"""Loopback-only synthetic acceptance server. NEVER loads a real user or database.

Used by the isolated Electron test. Governance identities below are test fixtures,
not authorizations. Real package integrity validation and Gateway execution are used.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
import io
import json
import os
from pathlib import Path
import zipfile

from fastapi import FastAPI
from fastapi.responses import Response


def create_fixture(cad_root: Path):
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.artifacts import ArtifactService, InMemoryArtifactStore, InMemoryObjectStorage
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.capability_v2.authorization import AuthorizationGrants
    from backend.capability_v2.reliability import ReliabilityCoordinator, InMemoryRateLimiter
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.contracts import ArtifactRef
    from backend.plugin_platform.manifest import parse_manifest
    from backend.plugin_platform.artifacts import validate_package
    from backend.plugin_platform.local_providers import InstalledProvider
    from backend.plugin_platform.provider_bindings import ApprovedLocalProvider
    from backend.plugin_platform.mounts import MountSessionService, InMemoryMountSessionStore
    from backend.tests.test_plugin_provider_bindings import binding_fixture
    from backend.routers import plugin_marketplace as router
    from backend.routers.deps import get_current_user,get_authenticated_principal
    from backend.capability_v2.identity import AuthenticatedPrincipal
    from backend.platform_sdk import artifacts as artifact_port
    from backend.plugin_platform import local_providers
    manifest=parse_manifest(json.loads((cad_root/'dist/huangjing.cad.layout-generator-0.1.0.release.json').read_text(encoding='utf-8')))
    package=(cad_root/'dist/huangjing.cad.layout-generator-0.1.0.zip').read_bytes()
    validate_package(package,manifest)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        source=archive.read('provider.mjs').decode()
        schemas=json.loads(archive.read('contracts.schema.json'))['$defs']
    _,fixture_catalog,_,_,_=binding_fixture()
    prototype=fixture_catalog.descriptors[0]
    providers=[]
    for declaration in manifest.provides:
        artifact=declaration.result=='artifact'
        def schema(name): return {'$ref':'#/$defs/'+name,'$defs':schemas}
        descriptor=prototype.model_copy(update={
            'id':declaration.id,'owner_domain':declaration.owner_domain,
            'input_schema':schema('ExportInput' if artifact else 'GenerateInput'),
            'output_schema':schema('ExportOutput' if artifact else 'GenerateOutput'),
            'provider_ref':f'{manifest.plugin_id}/provider.mjs#{declaration.export}',
            'capability_version_gid':'fixture-'+declaration.export,
        })
        if artifact:
            from backend.capability_v2.contracts import SideEffectLevel
            descriptor=descriptor.model_copy(update={'side_effect_level':SideEffectLevel.WRITE,
                'artifact_policy':'output','idempotency_policy':'required','consistency_policy':'external','replay_data_policy':'projected'})
        binding=ApprovedLocalProvider(manifest.plugin_id,manifest.version,manifest.artifact.sha256,declaration,descriptor,
            fixture_catalog.release_id,901,902,'sha256:'+'f'*64)
        providers.append(InstalledProvider(binding,'fixture-provider',1,source))
    catalog=build_release([]);store=InMemoryCatalogStore();store.publish(catalog)
    user={'gid':'fixture-user','team_id':'fixture-tenant','org_role':'member','is_active':True}
    principal=AuthenticatedPrincipal(user_id=user['gid'],authentication_method='isolated-fixture',authenticated_at=datetime.now(UTC))
    policy=LegacyServerGatewayPolicy(lambda _id:user,lambda _identity,_user:AuthorizationGrants(
        capability_scopes=tuple(item.id for item in manifest.provides),data_scopes=('internal',),tenant_id=user['team_id'],policy_version='fixture'))
    gateway=CapabilityGatewayService(CatalogResolver(store,CapabilityRegistry()),policy,
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(),InMemoryRateLimiter(limit=100))).bind_release(catalog.release_id)
    os.environ['AI00_PLUGIN_MOUNT_SECRET']='isolated-fixture-only-not-a-real-user-key'
    mounts=MountSessionService(InMemoryMountSessionStore())
    artifact_service=ArtifactService(InMemoryArtifactStore(),InMemoryObjectStorage())
    router.get_default_gateway=lambda:gateway
    router.installed_providers=lambda _user:tuple(providers)
    router._mount_service=lambda:mounts
    router.tenant_registry=lambda _user:[{'name':manifest.name,'plugin_id':manifest.plugin_id,'version':manifest.version,
        'web':manifest.runtimes['web'].model_dump(),'permissions':[],
        'capabilities':{'required':[{'id':item.id,'major':1} for item in manifest.provides]},
        'provides':[item.model_dump() for item in manifest.provides],
        'installation_id':'fixture-consumer','mount_revocation_version':1,'artifact':{'sha256':manifest.artifact.sha256}}]
    artifact_port.artifact_service=lambda:artifact_service
    local_providers.provider_commit_guard=lambda *_args:nullcontext()
    class Audit:
        def record(self,**_event): pass
    router.mount_invocation_audit=Audit()
    app=FastAPI()
    app.dependency_overrides[get_current_user]=lambda:user
    app.dependency_overrides[get_authenticated_principal]=lambda:principal
    app.include_router(router.router)
    @app.get('/fixture/ready')
    def ready(): return {'synthetic':True,'plugin_id':manifest.plugin_id,'artifact_sha256':manifest.artifact.sha256}
    @app.get('/api/v2/capability-artifacts/{artifact_id}/content')
    def content(artifact_id:str):
        # This server has no real credentials, user accounts or artifact storage.
        from backend.capability_v2.contracts import ActorIdentity,ConsumerIdentity,ConsumerDescriptor,TenantIdentity
        identity=ConsumerIdentity(actor=ActorIdentity(**principal.model_dump()),
            tenant=TenantIdentity(tenant_id=user['team_id'],membership='member'),consumer=ConsumerDescriptor(type='plugin',consumer_id=manifest.plugin_id))
        record=artifact_service.authorize_download(artifact_id,identity)
        return Response(artifact_service.read(record.artifact_ref,identity,maximum=32*1024*1024),media_type=record.artifact_ref.media_type)
    return app


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--cad-root',type=Path,required=True)
    args=parser.parse_args()
    import uvicorn
    uvicorn.run(create_fixture(args.cad_root),host='127.0.0.1',port=args.port,log_level='warning')
