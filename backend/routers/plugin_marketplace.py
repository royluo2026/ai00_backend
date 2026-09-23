"""Plugin marketplace catalog, publisher, review and runtime registry APIs."""
from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict

from backend.plugin_platform.artifacts import ArtifactError, publish_web_assets, read_web_asset, upload_to_ois, validate_package
from backend.plugin_platform.manifest import ManifestError, parse_manifest
from backend.plugin_platform.metrics import close_month, monthly_ranking
from backend.plugin_platform.mounts import (
    MountSessionError, MountSessionService, MountTokenError, SqlMountSessionStore, mount_url,
)
from backend.plugin_platform.invocation_audit import mount_invocation_audit
from backend.plugin_platform.service import finish_upgrade as finish_plugin_upgrade, list_catalog, list_installations, list_lifecycle_events, list_releases, register_publisher, resolve_asset_object_key, review_release, revoke_release, submit_release, tenant_registry, verify_submission_signature
from backend.plugin_platform.signing import SignatureError
from backend.routers.deps import build_profile, get_authenticated_principal, get_current_user
from backend.capability_v2.catalog import CatalogRelease, load_catalog_release
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.policies import GatewayPolicyError
from backend.plugin_platform.local_providers import installed_providers, local_jobs, finalize_generated_artifact
from backend.plugin_platform.provider_bindings import ProviderBindingError

router = APIRouter(prefix="/api/v1/plugin-marketplace", tags=["plugin-marketplace"])


def _manager(user: dict = Depends(get_current_user)) -> dict:
    if "system.plugin.manage" not in set(build_profile(user).get("permissions", [])):
        raise HTTPException(403, detail={"code": "permission_denied", "message": "system.plugin.manage is required"})
    return user


def _platform_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get('is_active') or 'super_admin' not in {user.get('system_role'), user.get('org_role')}:
        raise HTTPException(403, detail={'code': 'permission_denied', 'message': 'A super administrator is required'})
    return user


class PublisherRequest(BaseModel):
    publisher_id: str
    display_name: str = Field(min_length=1, max_length=255)
    public_key_pem: str = Field(min_length=80, max_length=4096)


class ReviewRequest(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=4000)
    release_sha256: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')


class UpgradeHealthRequest(BaseModel):
    healthy: bool


class MountInvokeRequest(BaseModel):
    payload: dict = Field(default_factory=dict)
    major_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    expected_resource_version: str | None = Field(default=None, max_length=255)
    approval_reference: str | None = Field(default=None, max_length=512)


def _mount_service() -> MountSessionService:
    from backend.db.connection import get_conn
    return MountSessionService(SqlMountSessionStore(get_conn))


def _catalog_release() -> CatalogRelease:
    # The running Gateway owns the validated snapshot, including test overlays.
    return get_default_gateway().catalog()


def _local_gateway(user, dispatch=None):
    providers = installed_providers(user)
    def handler(provider):
        async def execute(payload,context):
            if dispatch is None:
                raise ProviderBindingError("provider_app_transport_required")
            return await dispatch(provider,payload,context)
        return execute
    return get_default_gateway().with_local_providers(providers,handler)


def _resolved_mount_grants(item: dict, release: CatalogRelease) -> tuple[tuple[str, ...], tuple[str, ...]]:
    descriptors = {(value.id, value.major_version): value for value in release.descriptors}
    capability_contract = item.get("capabilities") or {}
    required = {
        (str(value.get("id")), int(value.get("major", 0)))
        for value in capability_contract.get("required") or ()
    }
    optional = {
        (str(value.get("id")), int(value.get("major", 0)))
        for value in capability_contract.get("optional") or ()
    }
    # Legacy permissions carry no major. They remain install metadata but do not
    # become V2 authority until a matching plugin-exposed descriptor exists.
    legacy = {(str(value), 1) for value in item.get("permissions") or ()}
    selected: list[str] = []
    missing_required: list[str] = []
    for capability_id, major in sorted(required | optional | legacy):
        descriptor = descriptors.get((capability_id, major))
        if descriptor is not None and descriptor.exposure.plugin:
            selected.append(f"{capability_id}@{major}")
        elif (capability_id, major) in required:
            missing_required.append(f"{capability_id}@{major}")
    return tuple(selected), tuple(missing_required)


def _mount_catalog(session, release: CatalogRelease) -> list[dict]:
    """Project the immutable Catalog to the mount's exact versioned grants."""
    granted = {
        (value.rsplit("@", 1)[0], int(value.rsplit("@", 1)[1]))
        for value in session.capability_grants
    }
    return [
        descriptor.model_dump(mode="json")
        for descriptor in release.descriptors
        if (descriptor.id, descriptor.major_version) in granted
        and descriptor.exposure.plugin
    ]


def _mount_data_scopes(grants: tuple[str, ...], release: CatalogRelease) -> tuple[str, ...]:
    granted = {
        (value.rsplit("@", 1)[0], int(value.rsplit("@", 1)[1])) for value in grants
    }
    return tuple(sorted({
        descriptor.data_classification
        for descriptor in release.descriptors
        if (descriptor.id, descriptor.major_version) in granted
    }))


def _plugin_identity(session, user: dict, principal) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(**principal.model_dump()),
        tenant=TenantIdentity(
            tenant_id=session.tenant_id, membership="member",
            active_roles=tuple(filter(None, (user.get("org_role"), user.get("system_role")))),
        ),
        consumer=ConsumerDescriptor(
            type=ConsumerType.PLUGIN, consumer_id=session.plugin_id,
            consumer_version=session.plugin_version, installation_id=session.installation_id,
            mount_session_id=session.mount_session_id,
        ),
    )


def _resolve_mount_for_user(mount_session_id: str, user: dict):
    tenant = user.get("team_id") or f"user:{user['gid']}"
    return _mount_service().resolve_for_user(
        mount_session_id, current_user_id=str(user["gid"]), current_tenant_id=tenant,
    )


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(400, detail={"code": "invalid_plugin_package", "message": str(exc)})


@router.get("/catalog")
def catalog(_user: dict = Depends(get_current_user)):
    return {"success": True, "data": list_catalog()}


@router.post("/usage/months/{month}/close")
def close_usage_month(month: str, user: dict = Depends(_manager)):
    try:
        data = close_month(user, month)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "invalid_usage_month", "message": str(exc)}) from exc
    return {"success": True, "data": data}


@router.get("/usage/months/{month}")
def usage_month(month: str, _user: dict = Depends(get_current_user)):
    try:
        data = monthly_ranking(_user, month)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "invalid_usage_month", "message": str(exc)}) from exc
    return {"success": True, "data": data}


@router.get("/installations")
def installations(user: dict = Depends(get_current_user)):
    return {"success": True, "data": list_installations(user)}


@router.get("/installations/{plugin_id}/events")
def installation_events(plugin_id: str, limit: int = Query(default=100, ge=1, le=500), user: dict = Depends(_manager)):
    return {"success": True, "data": list_lifecycle_events(user, plugin_id, limit)}


@router.post("/installations/{plugin_id}/upgrade-health")
def complete_installation_upgrade(
    plugin_id: str,
    body: UpgradeHealthRequest,
    user: dict = Depends(_manager),
):
    """Trusted manager callback after the staged release health check."""
    context = SimpleNamespace(user_gid=str(user["gid"]), team_gid=user.get("team_id"))
    try:
        data = finish_plugin_upgrade(
            {"plugin_id": plugin_id, "healthy": body.healthy}, context
        )
    except ValueError as exc:
        raise HTTPException(
            409,
            detail={"code": "plugin_upgrade_state_conflict", "message": str(exc)},
        ) from exc
    return {"success": True, "data": data}


@router.get("/registry")
def registry(
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    """Only enabled, signed tenant plugins are returned to the Web shell."""
    data = tenant_registry(user)
    tenant = user.get("team_id") or f"user:{user['gid']}"
    try:
        release = (_local_gateway(user).catalog() if any(item.get("provides") for item in data) else _catalog_release())
        service = _mount_service()
        for item in data:
            grants, missing_required = _resolved_mount_grants(item, release)
            installation_id = item.get("installation_id")
            revocation_version = int(item.get("mount_revocation_version") or 1)
            item.pop("installation_id", None)
            item.pop("mount_revocation_version", None)
            if not installation_id:
                item["mount_unavailable_reason"] = "installation_identity_missing_reinstall_required"
                continue
            if missing_required:
                item["mount_unavailable_reason"] = "required_capability_unavailable"
                item["missing_required_capabilities"] = missing_required
                continue
            issued = service.issue(
                user_id=str(user["gid"]), tenant_id=tenant,
                installation_id=str(installation_id), plugin_id=item["plugin_id"],
                plugin_version=item["version"], artifact_sha256=item["artifact"]["sha256"],
                catalog_release=release.release_id, capability_grants=grants,
                resource_scopes=(f"tenant:{tenant}",),
                data_scopes=_mount_data_scopes(grants, release),
                revocation_version=revocation_version,
                authenticated_at=principal.authenticated_at,
            )
            item["mount_session_id"] = issued.session.mount_session_id
            item["mount_expires_at"] = issued.session.expires_at.isoformat()
            item["catalog_release"] = release.release_id
            item["capability_grants"] = grants
            item["capability_versions"] = {
                value.rsplit("@", 1)[0]: int(value.rsplit("@", 1)[1]) for value in grants
            }
            item["capability_catalog"] = _mount_catalog(issued.session, release)
            item["mount_url"] = mount_url(
                issued.asset_token, item["plugin_id"], item["version"], item["web"]["entry"]
            )
    except (MountSessionError, MountTokenError) as exc:
        raise HTTPException(503, detail={"code": "plugin_mount_unavailable", "message": str(exc)}) from exc
    return {"success": True, "data": data}


class LocalJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret: str = Field(pattern=r"^[a-f0-9]{64}$")
    output: dict | None = None
    error: str | None = Field(default=None,max_length=128)


def _job_scope(session, user):
    return (str(user["gid"]),str(session.tenant_id),session.mount_session_id)


@router.post("/mounts/{mount_session_id}/capabilities/{capability_id}:local-start")
async def start_local_invocation(mount_session_id: str, capability_id: str, body: MountInvokeRequest,
    user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal)):
    try:
        session = _resolve_mount_for_user(mount_session_id,user)
        if f"{capability_id}@{body.major_version}" not in session.capability_grants:
            raise ProviderBindingError("capability_not_granted")
        request_id=f"plugin_{uuid.uuid4().hex}"
        envelope=InvocationEnvelope(capability_id=capability_id,major_version=body.major_version,
            catalog_release=session.catalog_release,payload=body.payload,identity=_plugin_identity(session,user,principal),
            idempotency_key=body.idempotency_key,expected_resource_version=body.expected_resource_version,
            approval_reference=body.approval_reference,request_id=request_id,trace_id=request_id)
        async def invoke(dispatch):
            async def execute(provider,payload,context):
                output = await dispatch(provider,payload,context)
                _resolve_mount_for_user(mount_session_id,user)
                # Re-read the current signed installation and current exact approval.
                current = next((item for item in installed_providers(user)
                    if item.binding == provider.binding and item.installation_id == provider.installation_id
                    and item.revision == provider.revision),None)
                if current is None:
                    raise ProviderBindingError("provider_binding_changed")
                gateway.reauthorize(envelope)
                if provider.binding.declaration.result == "artifact":
                    from backend.platform_sdk.artifacts import artifact_service
                    from backend.plugin_platform.local_providers import provider_commit_guard
                    with provider_commit_guard(user,session,provider):
                        return finalize_generated_artifact(output,envelope.identity,artifact_service())
                return output
            gateway=_local_gateway(user,execute)
            descriptor=gateway.catalog().descriptor(capability_id,body.major_version)
            if descriptor is None or descriptor.execution_mode.value!="local":
                raise ProviderBindingError("local_provider_unavailable")
            result=await gateway.invoke(envelope)
            mount_invocation_audit.record(session=session,capability_id=capability_id,
                major_version=body.major_version,request_id=request_id,payload=body.payload,
                status=result.status.value,error=result.error.code if result.error else None)
            return result.model_dump(mode="json")
        return local_jobs.start(_job_scope(session,user),invoke)
    except (MountSessionError,ProviderBindingError) as exc:
        raise HTTPException(403,detail={"code":"plugin_provider_denied","message":str(exc)}) from exc


@router.post("/mounts/{mount_session_id}/local-jobs/{job_id}/{action}")
async def local_job(mount_session_id: str, job_id: str, action: str, body: LocalJobRequest,
    user: dict=Depends(get_current_user)):
    try:
        session=_resolve_mount_for_user(mount_session_id,user)
        scope=_job_scope(session,user)
        if action=="poll": return local_jobs.poll(job_id,body.secret,scope)
        if action=="complete":
            local_jobs.complete(job_id,body.secret,scope,{"output":body.output,"error":body.error})
            return {"status":"received"}
        if action=="cancel":
            local_jobs.cancel(job_id,body.secret,scope)
            return {"status":"cancelled"}
        raise ProviderBindingError("provider_job_action_invalid")
    except (MountSessionError,ProviderBindingError) as exc:
        raise HTTPException(403,detail={"code":"plugin_provider_denied","message":str(exc)}) from exc


@router.post("/mounts/{mount_session_id}/capabilities/{capability_id}:invoke")
async def invoke_from_mount(
    mount_session_id: str,
    capability_id: str,
    body: MountInvokeRequest,
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    request_id = f"plugin_{uuid.uuid4().hex}"
    try:
        session = _resolve_mount_for_user(mount_session_id, user)
        if f"{capability_id}@{body.major_version}" not in session.capability_grants:
            mount_invocation_audit.record(
                session=session, capability_id=capability_id,
                major_version=body.major_version, request_id=request_id,
                payload=body.payload, status="denied", error="capability_not_granted",
            )
            raise MountSessionError("capability is not granted to this mount session")
    except MountSessionError as exc:
        raise HTTPException(403, detail={"code": "plugin_mount_denied", "message": str(exc)}) from exc
    gateway = get_default_gateway()
    if session.catalog_release != gateway.catalog_release:
        gateway = _local_gateway(user)
    result = await gateway.invoke(InvocationEnvelope(
        capability_id=capability_id,
        major_version=body.major_version,
        catalog_release=session.catalog_release,
        payload=body.payload,
        identity=_plugin_identity(session, user, principal),
        idempotency_key=body.idempotency_key,
        expected_resource_version=body.expected_resource_version,
        approval_reference=body.approval_reference,
        request_id=request_id,
        trace_id=request_id,
    ))
    mount_invocation_audit.record(
        session=session, capability_id=capability_id,
        major_version=body.major_version, request_id=request_id,
        payload=body.payload, status=result.status.value,
        error=result.error.code if result.error else None,
    )
    return result.model_dump(mode="json")


@router.post("/mounts/{mount_session_id}/capabilities/{capability_id}:confirm")
async def confirm_from_mount(
    mount_session_id: str,
    capability_id: str,
    body: MountInvokeRequest,
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    try:
        session = _resolve_mount_for_user(mount_session_id, user)
        if f"{capability_id}@{body.major_version}" not in session.capability_grants:
            raise MountSessionError("capability is not granted to this mount session")
        gateway = get_default_gateway()
        if session.catalog_release != gateway.catalog_release:
            gateway = _local_gateway(user)
        request_id = f"plugin_approval_{uuid.uuid4().hex}"
        issued = await gateway.request_approval(InvocationEnvelope(
            capability_id=capability_id, major_version=body.major_version,
            catalog_release=session.catalog_release, payload=body.payload,
            identity=_plugin_identity(session, user, principal),
            idempotency_key=body.idempotency_key,
            expected_resource_version=body.expected_resource_version,
            request_id=request_id, trace_id=request_id,
        ))
    except MountSessionError as exc:
        raise HTTPException(403, detail={"code": "plugin_mount_denied", "message": str(exc)}) from exc
    except GatewayPolicyError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": exc.message}) from exc
    # This endpoint is called by the trusted Host approval loop, never forwarded
    # through postMessage to the plugin iframe.
    return {
        "approval_reference": issued.token,
        "approval_id": issued.challenge.approval_id,
        "expires_at": issued.challenge.expires_at,
    }


@router.post("/publishers")
def create_publisher(body: PublisherRequest, user: dict = Depends(_platform_admin)):
    try:
        data = register_publisher(body.publisher_id, body.display_name, body.public_key_pem, user["gid"])
    except (ValueError, SignatureError) as exc:
        raise _bad(exc) from exc
    return {"success": True, "data": data}


@router.post("/releases")
async def create_release(
    manifest_json: str = Form(...), publisher_signature: str = Form(...),
    package: UploadFile = File(...), user: dict = Depends(_platform_admin),
):
    try:
        manifest = parse_manifest(json.loads(manifest_json))
        verify_submission_signature(manifest.model_dump(mode="json"), publisher_signature)
        data = await package.read(manifest.artifact.size + 1)
        validate_package(data, manifest)
        upload_to_ois(data, manifest)
        publish_web_assets(data, manifest)
        result = submit_release(manifest.model_dump(mode="json"), publisher_signature, user["gid"])
    except (ValueError, ManifestError, SignatureError, ArtifactError, json.JSONDecodeError) as exc:
        raise _bad(exc) from exc
    finally:
        await package.close()
    return {"success": True, "data": result}


@router.get("/releases")
def releases(status: str | None = Query(default=None), user: dict = Depends(_platform_admin)):
    try:
        data = list_releases(status)
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"success": True, "data": data}

@router.post("/releases/{plugin_id}/{version}/review")
def review(plugin_id: str, version: str, body: ReviewRequest, user: dict = Depends(_platform_admin)):
    try:
        data = review_release(plugin_id, version, body.approved, body.note, user["gid"], expected_sha256=body.release_sha256)
    except (ValueError, SignatureError) as exc:
        raise _bad(exc) from exc
    return {"success": True, "data": data}


@router.post("/releases/{plugin_id}/{version}/revoke")
def revoke(plugin_id: str, version: str, body: ReviewRequest, user: dict = Depends(_platform_admin)):
    try:
        data = revoke_release(plugin_id, version, body.note or "security revocation", user["gid"], expected_sha256=body.release_sha256)
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"success": True, "data": data}


@router.get("/assets/{token}/{plugin_id}/{version}/{asset_path:path}", include_in_schema=False)
def plugin_asset(token: str, plugin_id: str, version: str, asset_path: str):
    try:
        claims = _mount_service().resolve_asset_token(
            token, expected_plugin_id=plugin_id, expected_version=version
        )
        object_key = resolve_asset_object_key(claims, asset_path)
        content = read_web_asset(object_key)
    except (MountTokenError, MountSessionError) as exc:
        raise HTTPException(403, detail={"code": "invalid_plugin_mount", "message": str(exc)}) from exc
    except PermissionError as exc:
        raise HTTPException(410, detail={"code": "plugin_mount_revoked", "message": str(exc)}) from exc
    except ArtifactError as exc:
        raise HTTPException(502, detail={"code": "plugin_asset_unavailable", "message": str(exc)}) from exc
    headers = {
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Cross-Origin-Resource-Policy": "cross-origin", "Access-Control-Allow-Origin": "*",
        "Cache-Control": "private, no-store",
    }
    media_type = mimetypes.guess_type(asset_path)[0] or "application/octet-stream"
    return Response(content=content, media_type=media_type, headers=headers)
