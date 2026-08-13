"""Plugin marketplace catalog, publisher, review and runtime registry APIs."""
from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.plugin_platform.artifacts import ArtifactError, publish_web_assets, read_web_asset, upload_to_ois, validate_package
from backend.plugin_platform.manifest import ManifestError, parse_manifest
from backend.plugin_platform.metrics import close_month, monthly_ranking
from backend.plugin_platform.mounts import (
    MountSessionError, MountSessionService, MountTokenError, SqlMountSessionStore, mount_url,
)
from backend.plugin_platform.invocation_audit import mount_invocation_audit
from backend.plugin_platform.service import list_catalog, list_installations, list_lifecycle_events, list_releases, register_publisher, resolve_asset_object_key, review_release, revoke_release, submit_release, tenant_registry, verify_submission_signature
from backend.plugin_platform.signing import SignatureError
from backend.routers.deps import build_profile, get_authenticated_principal, get_current_user
from backend.capability_v2.catalog import CatalogRelease
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.policies import GatewayPolicyError

router = APIRouter(prefix="/api/v1/plugin-marketplace", tags=["plugin-marketplace"])


def _manager(user: dict = Depends(get_current_user)) -> dict:
    if "system.plugin.manage" not in set(build_profile(user).get("permissions", [])):
        raise HTTPException(403, detail={"code": "permission_denied", "message": "system.plugin.manage is required"})
    return user


class PublisherRequest(BaseModel):
    publisher_id: str
    display_name: str = Field(min_length=1, max_length=255)
    public_key_pem: str = Field(min_length=80, max_length=4096)


class ReviewRequest(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=4000)


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
    path = Path(__file__).resolve().parents[2] / "docs/governance/capability-catalog-release.json"
    release = CatalogRelease.model_validate_json(path.read_text(encoding="utf-8"))
    if release.release_id != get_default_gateway().catalog_release:
        raise MountSessionError("gateway and plugin mount catalog releases differ")
    return release


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


@router.get("/registry")
def registry(
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    """Only enabled, signed tenant plugins are returned to the Web shell."""
    data = tenant_registry(user)
    tenant = user.get("team_id") or f"user:{user['gid']}"
    try:
        release = _catalog_release()
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
def create_publisher(body: PublisherRequest, user: dict = Depends(_manager)):
    try:
        data = register_publisher(body.publisher_id, body.display_name, body.public_key_pem, user["gid"])
    except (ValueError, SignatureError) as exc:
        raise _bad(exc) from exc
    return {"success": True, "data": data}


@router.post("/releases")
async def create_release(
    manifest_json: str = Form(...), publisher_signature: str = Form(...),
    package: UploadFile = File(...), user: dict = Depends(_manager),
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
def releases(status: str | None = Query(default=None), user: dict = Depends(_manager)):
    try:
        data = list_releases(status)
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"success": True, "data": data}

@router.post("/releases/{plugin_id}/{version}/review")
def review(plugin_id: str, version: str, body: ReviewRequest, user: dict = Depends(_manager)):
    try:
        data = review_release(plugin_id, version, body.approved, body.note, user["gid"])
    except (ValueError, SignatureError) as exc:
        raise _bad(exc) from exc
    return {"success": True, "data": data}


@router.post("/releases/{plugin_id}/{version}/revoke")
def revoke(plugin_id: str, version: str, body: ReviewRequest, user: dict = Depends(_manager)):
    try:
        data = revoke_release(plugin_id, version, body.note or "security revocation", user["gid"])
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
