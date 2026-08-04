"""Plugin marketplace catalog, publisher, review and runtime registry APIs."""
from __future__ import annotations

import json
import mimetypes
import requests

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.plugin_platform.artifacts import ArtifactError, publish_web_assets, upload_to_ois, validate_package
from backend.plugin_platform.manifest import ManifestError, parse_manifest
from backend.plugin_platform.metrics import close_month, monthly_ranking
from backend.plugin_platform.mounts import MountTokenError, issue_mount_token, mount_url, verify_mount_token
from backend.plugin_platform.service import list_catalog, list_installations, list_lifecycle_events, list_releases, register_publisher, resolve_asset_object_key, review_release, revoke_release, submit_release, tenant_registry, verify_submission_signature
from backend.plugin_platform.signing import SignatureError
from backend.routers.deps import build_profile, get_current_user

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
def registry(user: dict = Depends(get_current_user)):
    """Only enabled, signed tenant plugins are returned to the Web shell."""
    data = tenant_registry(user)
    tenant = user.get("team_id") or f"user:{user['gid']}"
    try:
        for item in data:
            token = issue_mount_token(tenant_gid=tenant, plugin_id=item["plugin_id"], version=item["version"], artifact_sha256=item["artifact"]["sha256"])
            item["mount_url"] = mount_url(token, item["plugin_id"], item["version"], item["web"]["entry"])
    except MountTokenError as exc:
        raise HTTPException(503, detail={"code": "plugin_mount_unavailable", "message": str(exc)}) from exc
    return {"success": True, "data": data}


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
    upstream = None
    try:
        claims = verify_mount_token(token)
        if claims.plugin_id != plugin_id or claims.version != version: raise MountTokenError("mount route does not match token")
        object_key = resolve_asset_object_key(claims, asset_path)
        from backend.core import ois_storage
        access_url = ois_storage.generate_access_url(object_key, 60)
        if not access_url: raise ArtifactError("OIS asset is unavailable")
        upstream = requests.get(access_url, stream=True, timeout=(5, 30))
        if upstream.status_code != 200: raise ArtifactError(f"OIS asset returned {upstream.status_code}")
        length = int(upstream.headers.get("Content-Length") or 0)
        if length > 25 * 1024 * 1024: raise ArtifactError("plugin asset exceeds response limit")
        chunks, total = [], 0
        for chunk in upstream.iter_content(64 * 1024):
            if not chunk: continue
            total += len(chunk)
            if total > 25 * 1024 * 1024: raise ArtifactError("plugin asset exceeds response limit")
            chunks.append(chunk)
        content = b"".join(chunks)
        upstream.close(); upstream = None
    except MountTokenError as exc:
        if upstream: upstream.close()
        raise HTTPException(403, detail={"code": "invalid_plugin_mount", "message": str(exc)}) from exc
    except PermissionError as exc:
        if upstream: upstream.close()
        raise HTTPException(410, detail={"code": "plugin_mount_revoked", "message": str(exc)}) from exc
    except (ArtifactError, requests.RequestException) as exc:
        if upstream: upstream.close()
        raise HTTPException(502, detail={"code": "plugin_asset_unavailable", "message": str(exc)}) from exc
    headers = {
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Cross-Origin-Resource-Policy": "cross-origin", "Access-Control-Allow-Origin": "*",
        "Cache-Control": "private, no-store",
    }
    media_type = mimetypes.guess_type(asset_path)[0] or "application/octet-stream"
    return Response(content=content, media_type=media_type, headers=headers)
