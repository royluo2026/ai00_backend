import asyncio
import base64
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from backend.plugin_platform.local_providers import (
    LocalInvocationJobs, InstalledProvider, finalize_generated_artifact, decode_generated_artifact,
)
from backend.plugin_platform.provider_bindings import resolve_provider_bindings, ProviderBindingError
from backend.tests.test_plugin_provider_bindings import binding_fixture


def fixture_provider():
    manifest,release,store,_,_=binding_fixture()
    binding,=resolve_provider_bindings(manifest,release,store)
    return InstalledProvider(binding,"fixture-install",1,"export function generate(){return {}}")


def test_same_app_jobs_reject_other_actor_mount_secret_and_replay():
    async def scenario():
        broker=LocalInvocationJobs()
        scope=("user-a","tenant-a","mount-a")
        async def invoke(dispatch): return await dispatch(fixture_provider(),{},None)
        job=broker.start(scope,invoke)
        await asyncio.sleep(.01)
        for wrong in [("user-b","tenant-a","mount-a"),("user-a","tenant-b","mount-a"),("user-a","tenant-a","mount-b")]:
            with pytest.raises(ProviderBindingError): broker.poll(job["job_id"],job["secret"],wrong)
        with pytest.raises(ProviderBindingError): broker.poll(job["job_id"],"0"*64,scope)
        command=broker.poll(job["job_id"],job["secret"],scope)
        assert command["status"]=="execute"
        assert "identity" not in command["command"]["context"]
        assert broker.poll(job["job_id"],job["secret"],scope)["status"]=="pending"
        broker.complete(job["job_id"],job["secret"],scope,{"output":{"echo":1}})
        with pytest.raises(ProviderBindingError): broker.complete(job["job_id"],job["secret"],scope,{"output":{}})
        await asyncio.sleep(.01)
        assert broker.poll(job["job_id"],job["secret"],scope)=={"status":"completed","result":{"echo":1}}
        assert not broker.jobs
    asyncio.run(scenario())


def test_gateway_preserves_original_plugin_identity_and_denies_ungranted_call():
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.catalog import build_release,CatalogResolver
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import LegacyServerGatewayPolicy
    from backend.capability_v2.authorization import AuthorizationGrants
    from backend.capability_v2.contracts import InvocationEnvelope, ConsumerType
    from backend.tests.test_capability_gateway_pipeline import _identity
    async def scenario():
        provider=fixture_provider();calls=[];allowed=[True]
        catalog=build_release([]);store=InMemoryCatalogStore();store.publish(catalog)
        policy=LegacyServerGatewayPolicy(lambda _user:{"is_active":True},lambda identity,_user:AuthorizationGrants(
            capability_scopes=(provider.binding.descriptor.id,) if allowed[0] else (),
            resource_scopes=(),data_scopes=("internal",),tenant_id=identity.tenant.tenant_id,policy_version="fixture"))
        gateway=CapabilityGatewayService(CatalogResolver(store,CapabilityRegistry()),policy).bind_release(catalog.release_id)
        async def handler(payload,context):
            calls.append((context.plugin_id,context.source,context.team_gid));return {}
        scoped=gateway.with_local_providers([provider],lambda _provider:handler)
        identity=_identity(ConsumerType.PLUGIN)
        identity=identity.model_copy(update={"consumer":identity.consumer.model_copy(update={
            "consumer_id":"acme.consumer.ui","installation_id":"consumer-install","mount_session_id":"consumer-mount"})})
        envelope=InvocationEnvelope(capability_id=provider.binding.descriptor.id,major_version=1,
            catalog_release=scoped.catalog_release,payload={},identity=identity,request_id="fixture-call",trace_id="fixture-call")
        result=await scoped.invoke(envelope)
        assert result.ok,result
        assert calls==[("acme.consumer.ui","plugin","tenant_1")]
        allowed[0]=False
        denied=await scoped.invoke(envelope)
        assert not denied.ok and denied.error.code=="consumer_capability_scope_denied"
        assert len(calls)==1
        assert gateway.catalog().descriptors==()
    asyncio.run(scenario())


def test_generated_artifact_is_finalized_with_original_tenant_and_hash():
    from backend.capability_v2.artifacts import ArtifactService,InMemoryArtifactStore,InMemoryObjectStorage,ArtifactAuthorizationError
    from backend.capability_v2.contracts import ArtifactRef
    from backend.tests.test_artifact_operation_protocol import identity
    service=ArtifactService(InMemoryArtifactStore(),InMemoryObjectStorage())
    data=b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
    output={"file_name":"fixture.dxf","media_type":"image/vnd.dxf","content_base64":base64.b64encode(data).decode()}
    result=finalize_generated_artifact(output,identity(),service)
    assert result["file_name"]=="fixture.dxf"
    ref=ArtifactRef.model_validate(result["artifact_ref"])
    assert service.read(ref,identity(),maximum=1024)==data
    with pytest.raises(ArtifactAuthorizationError): service.read(ref,identity(tenant="tenant-b"),maximum=1024)
    for patch in [{"file_name":"../bad.dxf"},{"media_type":"text/html"},{"content_base64":"bad"},{"artifact_ref":{}}]:
        with pytest.raises(ProviderBindingError): decode_generated_artifact({**output,**patch})


def test_provider_catalog_rejects_duplicate_and_stale_release():
    from backend.plugin_platform.local_providers import LocalProviderResolver
    from backend.capability_v2.catalog import build_release,CatalogResolutionError
    provider=fixture_provider();base=build_release([])
    resolver=LocalProviderResolver(None,base,[provider],lambda _p:lambda *_args:{})
    with pytest.raises(ProviderBindingError): LocalProviderResolver(None,base,[provider,provider],lambda _p:None)
    with pytest.raises(CatalogResolutionError): resolver.catalog(base.release_id)


def test_local_artifact_gateway_replay_does_not_repeat_effect():
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.catalog import build_release,CatalogResolver
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.policies import FailClosedGatewayPolicy
    from backend.capability_v2.reliability import ReliabilityCoordinator,InMemoryRateLimiter
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.contracts import InvocationEnvelope,ConsumerType,SideEffectLevel
    from backend.tests.test_capability_gateway_pipeline import _identity
    async def scenario():
        provider=fixture_provider();effects=[]
        descriptor=provider.binding.descriptor.model_copy(update={'side_effect_level':SideEffectLevel.WRITE,
            'consistency_policy':'external','idempotency_policy':'required','replay_data_policy':'projected'})
        provider=replace(provider,binding=replace(provider.binding,descriptor=descriptor))
        base=build_release([]);store=InMemoryCatalogStore();store.publish(base)
        gateway=CapabilityGatewayService(CatalogResolver(store,CapabilityRegistry()),FailClosedGatewayPolicy(),
            reliability=ReliabilityCoordinator(InMemoryOutcomeStore(),InMemoryRateLimiter(limit=10))).bind_release(base.release_id)
        async def handler(payload,context): effects.append(context.idempotency_key);return {}
        scoped=gateway.with_local_providers([provider],lambda _p:handler)
        identity=_identity(ConsumerType.PLUGIN)
        envelope=InvocationEnvelope(capability_id=descriptor.id,major_version=1,catalog_release=scoped.catalog_release,
            payload={},identity=identity,idempotency_key='same-user-attempt',request_id='fixture-replay',trace_id='fixture-replay')
        first=await scoped.invoke(envelope);second=await scoped.invoke(envelope)
        assert first.ok and second.ok,(first,second)
        assert effects==['same-user-attempt']
    asyncio.run(scenario())


def test_local_http_route_discards_output_when_provider_disabled(monkeypatch):
    from datetime import UTC,datetime
    from backend.routers import plugin_marketplace as router
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.catalog import build_release,CatalogResolver
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.identity import AuthenticatedPrincipal
    async def scenario():
        provider=fixture_provider();active=[True]
        base=build_release([]);store=InMemoryCatalogStore();store.publish(base)
        gateway=CapabilityGatewayService(CatalogResolver(store,CapabilityRegistry())).bind_release(base.release_id)
        monkeypatch.setattr(router,'get_default_gateway',lambda:gateway)
        monkeypatch.setattr(router,'installed_providers',lambda _user:(provider,) if active[0] else ())
        scoped=router._local_gateway({'gid':'user','team_id':'tenant'})
        session=NS(mount_session_id='mount-fixture',tenant_id='tenant',plugin_id='acme.consumer.ui',
            plugin_version='1.0.0',installation_id='consumer-install',catalog_release=scoped.catalog_release,
            capability_grants=(provider.binding.descriptor.id+'@1',))
        monkeypatch.setattr(router,'_resolve_mount_for_user',lambda *_args:session)
        monkeypatch.setattr(router,'mount_invocation_audit',NS(record=lambda **_kwargs:None))
        monkeypatch.setattr(router,'local_jobs',LocalInvocationJobs())
        user={'gid':'user','team_id':'tenant'}
        principal=AuthenticatedPrincipal(user_id='user',authentication_method='fixture',authenticated_at=datetime.now(UTC))
        started=await router.start_local_invocation('mount-fixture',provider.binding.descriptor.id,
            router.MountInvokeRequest(payload={},major_version=1),user,principal)
        scope=router._job_scope(session,user)
        await asyncio.sleep(.01)
        assert router.local_jobs.poll(started['job_id'],started['secret'],scope)['status']=='execute'
        active[0]=False
        router.local_jobs.complete(started['job_id'],started['secret'],scope,{'output':{}})
        await asyncio.sleep(.01)
        result=router.local_jobs.poll(started['job_id'],started['secret'],scope)['result']
        assert result['ok'] is False
    asyncio.run(scenario())
