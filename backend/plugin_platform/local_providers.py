"""Same-App local computation adapter; Catalog/Gateway retain all authority."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass

from backend.capabilities.models_next import CapabilitySpec, CapabilityBusinessError
from backend.capabilities.registry_next import RegisteredCapability
from backend.capability_v2.catalog import build_release, CatalogResolutionError
from backend.capability_v2.contracts import CapabilityDescriptorV2
from .manifest import parse_manifest, PluginManifestV21
from .provider_bindings import resolve_provider_bindings, ProviderBindingError


def approved_manifest_bindings(manifest):
    from backend.db.connection import get_conn, acquire_connection
    from backend.capability_governance_test.store import SqlGovernanceStore
    from backend.capability_v2.catalog_store import SqlCatalogStore
    with get_conn() as conn:
        store = SqlGovernanceStore(conn)
        snapshot = store.latest_snapshot()
        if snapshot is None:
            raise ProviderBindingError("provider_snapshot_missing")
        release = SqlCatalogStore(acquire_connection).get(snapshot.document.product_release_id)
        if release is None:
            raise ProviderBindingError("provider_catalog_missing")
        return resolve_provider_bindings(manifest, release, store)


@dataclass(frozen=True)
class InstalledProvider:
    binding: object
    installation_id: str
    revision: int
    source: str


def installed_providers(user):
    """No global registry mutations: two tenants may pin different artifacts."""
    return providers_for_tenant(user.get("team_id") or f"user:{user['gid']}")


def providers_for_tenant(tenant):
    from backend.db.connection import get_conn
    from .service import _decode, platform_public_key
    from .signing import canonical_release, verify
    from .artifacts import validate_package
    from backend.core import storage
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT i.installation_id,i.mount_revocation_version,r.manifest,r.platform_signature "
                "FROM workmanship_plugin_installations i JOIN workmanship_plugin_releases r "
                "ON r.plugin_id=i.plugin_id AND r.version=i.current_version "
                "WHERE i.tenant_gid=%s AND i.state IN ('enabled','rolled_back') AND r.status='published'",
                (tenant,),
            )
            rows = list(cur.fetchall())
    providers = []
    for row in rows:
        raw = _decode(row["manifest"])
        if raw.get("schema_version") != "2.1":
            continue
        manifest = parse_manifest(raw)
        verify(platform_public_key(), canonical_release(raw, manifest.artifact.sha256), row["platform_signature"])
        try:
            bindings = approved_manifest_bindings(manifest)
        except ProviderBindingError:
            # Installed UI may remain visible, but unapproved capabilities are absent.
            continue
        package = storage.get_immutable(manifest.artifact.object_key)
        if package is None:
            raise ProviderBindingError("provider_package_missing")
        validate_package(package, manifest)
        import zipfile
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            for binding in bindings:
                providers.append(InstalledProvider(binding, str(row["installation_id"]),
                    int(row["mount_revocation_version"]), archive.read(binding.declaration.module).decode("utf-8")))
    return tuple(providers)


class LocalProviderResolver:
    """An invocation-local Catalog extension. Official providers still use their resolver."""
    def __init__(self, base_resolver, base_release, providers, handler_factory):
        self.base_resolver, self.base_release = base_resolver, base_release
        self.providers = {}
        descriptors = list(base_release.descriptors)
        artifacts = list(base_release.provider_artifacts)
        from backend.capability_v2.catalog import ProviderArtifact
        for provider in providers:
            binding = provider.binding
            descriptor = binding.descriptor
            key = (descriptor.id, descriptor.major_version)
            if base_release.descriptor(*key) or key in self.providers:
                raise ProviderBindingError("provider_capability_conflict")
            spec = CapabilitySpec(id=descriptor.id, version=descriptor.major_version, owner=descriptor.owner_domain,
                execution="local", risk=descriptor.side_effect_level.value, confirmation=descriptor.confirmation_policy,
                plugin_callable=True, input_schema=descriptor.input_schema, output_schema=descriptor.output_schema)
            self.providers[key] = RegisteredCapability(spec, handler_factory(provider), descriptor)
            descriptors.append(descriptor)
            artifact = ProviderArtifact(plugin_id=binding.plugin_id,module="local.javascript",version=binding.plugin_version,
                artifact_hash="sha256:"+binding.artifact_sha256)
            if artifact not in artifacts:
                artifacts.append(artifact)
        self.release = build_release(descriptors, artifacts)

    def catalog(self, release_id):
        if release_id != self.release.release_id:
            raise CatalogResolutionError("local_provider_catalog_changed")
        return self.release

    def descriptor(self, release_id, capability_id, major_version):
        descriptor = self.catalog(release_id).descriptor(capability_id, major_version)
        if descriptor is None:
            raise CatalogResolutionError("capability_not_in_release")
        return descriptor

    def resolve(self, release_id, capability_id, major_version):
        self.descriptor(release_id, capability_id, major_version)
        return self.providers.get((capability_id, major_version)) or self.base_resolver.resolve(
            self.base_release.release_id, capability_id, major_version)


class LocalInvocationJobs:
    """Bounded, ephemeral rendezvous. Secrets and source never enter plugin frames.

    A restart invalidates jobs; durable write outcome/replay remains the Gateway's.
    A job is tied to its original actor, tenant, mount and unguessable App secret.
    """
    def __init__(self):
        self.jobs = {}

    def start(self, scope, invoke):
        self.expire()
        if len(self.jobs) >= 8 or sum(job["scope"][:2] == scope[:2] for job in self.jobs.values()) >= 4:
            raise ProviderBindingError("provider_busy")
        job_id, secret = secrets.token_hex(16), secrets.token_hex(32)
        job = {"scope":scope,"secret":secret,"expires":time.monotonic()+65,"command":None,
            "response":asyncio.get_running_loop().create_future(),"claimed":False}
        self.jobs[job_id] = job
        async def dispatch(provider, payload, context):
            binding, descriptor = provider.binding, provider.binding.descriptor
            job["command"] = {"source":provider.source,"export_name":binding.declaration.export,
                "payload":payload,"context":{"plugin_id":binding.plugin_id,"plugin_version":binding.plugin_version,
                    "provider_artifact_sha256":binding.artifact_sha256},
                "timeout_ms":min(descriptor.timeout_seconds*1000,60000),
                "allowed_errors":[item.code for item in descriptor.domain_errors],
                "max_output_bytes":48*1024*1024 if binding.declaration.result=="artifact" else descriptor.execution_budget.max_output_bytes}
            response = await asyncio.wait_for(job["response"], min(descriptor.timeout_seconds,60))
            if response.get("error"):
                declared=next((item for item in descriptor.domain_errors if item.code==response["error"]),None)
                if declared:
                    raise CapabilityBusinessError(declared.code,declared.meaning,retryable=declared.retryable)
                raise CapabilityBusinessError("plugin.provider.execution_failed", "Local provider execution failed.")
            return response["output"]
        async def run():
            return await asyncio.wait_for(invoke(dispatch),60)
        job["task"] = asyncio.create_task(run())
        return {"job_id":job_id,"secret":secret}

    def expire(self):
        for key,job in tuple(self.jobs.items()):
            if time.monotonic() >= job["expires"]:
                job["task"].cancel()
                self.jobs.pop(key,None)

    def get(self, job_id, secret, scope):
        self.expire()
        job = self.jobs.get(job_id)
        if not job or job["scope"] != scope or not secrets.compare_digest(job["secret"],secret):
            raise ProviderBindingError("provider_job_denied")
        return job

    def poll(self, job_id, secret, scope):
        job = self.get(job_id,secret,scope)
        if job["task"].done():
            self.jobs.pop(job_id)
            try:
                result = job["task"].result()
            except (Exception,asyncio.CancelledError):
                raise ProviderBindingError("provider_execution_failed") from None
            return {"status":"completed","result":result}
        if job["command"] is not None and not job["claimed"]:
            job["claimed"] = True
            return {"status":"execute","command":job["command"]}
        return {"status":"pending"}

    def complete(self, job_id, secret, scope, response):
        job = self.get(job_id,secret,scope)
        if not job["claimed"] or job["response"].done():
            raise ProviderBindingError("provider_job_already_completed")
        if len(json.dumps(response,ensure_ascii=False).encode())>48*1024*1024:
            raise ProviderBindingError("provider_output_limit")
        job["response"].set_result(response)

    def cancel(self, job_id, secret, scope):
        job = self.get(job_id,secret,scope)
        job["task"].cancel()
        self.jobs.pop(job_id,None)


def decode_generated_artifact(output):
    if not isinstance(output,dict) or set(output)!={"file_name","media_type","content_base64"}:
        raise ProviderBindingError("provider_artifact_invalid")
    name, media, encoded = output["file_name"], output["media_type"], output["content_base64"]
    import re
    if not isinstance(name,str) or not re.fullmatch(r"[^/\\\x00-\x1f:]{1,200}",name):
        raise ProviderBindingError("provider_artifact_name_invalid")
    if not isinstance(encoded,str) or len(encoded)>44739244:
        raise ProviderBindingError("provider_artifact_size_invalid")
    try:
        data = base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError):
        raise ProviderBindingError("provider_artifact_encoding_invalid") from None
    if not data or len(data)>32*1024*1024:
        raise ProviderBindingError("provider_artifact_size_invalid")
    # Inert drawing formats only; never HTML, executable scripts or external URLs.
    if media=="image/jpeg":
        valid=name.lower().endswith((".jpg",".jpeg")) and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    elif media=="image/vnd.dxf":
        valid=name.lower().endswith(".dxf") and b"SECTION" in data[:100] and data.rstrip().endswith(b"EOF")
    else:
        valid=False
    if not valid:
        raise ProviderBindingError("provider_artifact_media_invalid")
    return name, media, data


def finalize_generated_artifact(output, identity, service):
    name, media, data = decode_generated_artifact(output)
    digest = hashlib.sha256(data).hexdigest()
    upload = service.create_upload(identity,media_type=media,expected_sha256=digest,expected_byte_size=len(data))
    service.upload_stream(upload.upload_id,identity,io.BytesIO(data))
    ref=service.finalize(upload.upload_id,identity,reported_sha256=digest)
    return {"artifact_ref":ref.model_dump(mode="json"),"file_name":name}


local_jobs = LocalInvocationJobs()


def revalidate_locked_provider(conn, binding, raw_manifest):
    from backend.db.connection import acquire_connection
    from backend.capability_governance_test.store import SqlGovernanceStore
    from backend.capability_v2.catalog_store import SqlCatalogStore
    from .service import _decode
    manifest=parse_manifest(_decode(raw_manifest))
    release=SqlCatalogStore(acquire_connection).get(binding.catalog_release)
    if release is None or binding not in resolve_provider_bindings(manifest,release,SqlGovernanceStore(conn)):
        raise ProviderBindingError('provider_binding_changed')


@contextmanager
def provider_commit_guard(user, session, provider):
    """Serialize artifact publication against producer/consumer lifecycle changes."""
    from backend.db.connection import get_conn
    tenant=user.get("team_id") or f"user:{user['gid']}"
    expected={session.installation_id:(session.plugin_version,session.revocation_version),
        provider.installation_id:(provider.binding.plugin_version,provider.revision)}
    with get_conn() as conn:
        with conn.cursor() as cursor:
            from backend.capability_governance_test.runtime_fence import acquire_runtime_fence
            acquire_runtime_fence(cursor,required=True)
            for installation_id,(version,revision) in sorted(expected.items()):
                cursor.execute("SELECT current_version,mount_revocation_version,state FROM workmanship_plugin_installations "
                    "WHERE tenant_gid=%s AND installation_id=%s FOR UPDATE",(tenant,installation_id))
                row=cursor.fetchone()
                if (not row or row["current_version"]!=version or int(row["mount_revocation_version"])!=revision
                        or row["state"] not in {"enabled","rolled_back"}):
                    raise ProviderBindingError("provider_binding_changed")
            cursor.execute("SELECT status,artifact_sha256,manifest FROM workmanship_plugin_releases "
                "WHERE plugin_id=%s AND version=%s FOR UPDATE",(provider.binding.plugin_id,provider.binding.plugin_version))
            row=cursor.fetchone()
            if not row or row["status"]!="published" or row["artifact_sha256"]!=provider.binding.artifact_sha256:
                raise ProviderBindingError("provider_binding_changed")
            revalidate_locked_provider(conn,provider.binding,row['manifest'])
            yield
