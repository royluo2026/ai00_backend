"""Authenticated HTTP transport for governed ArtifactRef upload/download sessions."""
from __future__ import annotations

import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.capability_v2.artifacts import (
    ArtifactAuthorizationError,
    ArtifactError,
    ArtifactIntegrityError,
    ArtifactService,
    OisObjectStorage,
    SqlArtifactStore,
)
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, TenantIdentity,
)
from backend.db.connection import get_conn
from backend.routers.deps import (
    build_capability_authorization_grants, get_authenticated_principal, get_current_user,
)


router = APIRouter(prefix="/api/v2/capability-artifacts", tags=["capability-artifacts"])


class CreateUploadRequest(BaseModel):
    media_type: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0, le=20 * 1024 * 1024 * 1024)
    resource_refs: tuple[str, ...] = ()


class FinalizeUploadRequest(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _identity(user: dict, principal) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(**principal.model_dump()),
        tenant=TenantIdentity(
            tenant_id=str(user.get("team_id") or "default"), membership="member",
            active_roles=tuple(filter(None, (user.get("org_role"), user.get("system_role")))),
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )


def _service() -> ArtifactService:
    return ArtifactService(SqlArtifactStore(get_conn), OisObjectStorage())


def _granted_resources(user: dict, identity: ConsumerIdentity) -> tuple[str, ...]:
    return build_capability_authorization_grants(
        user, identity.tenant.tenant_id, "web"
    ).resource_scopes


def _assert_resources_allowed(requested: tuple[str, ...], granted: tuple[str, ...]) -> None:
    for ref in requested:
        resource_type = ref.split(":", 1)[0]
        if "*" not in granted and ref not in granted and f"{resource_type}:*" not in granted:
            raise HTTPException(status_code=403, detail={"code": "resource_scope_denied"})


def _raise_artifact_error(exc: ArtifactError) -> None:
    if isinstance(exc, ArtifactAuthorizationError):
        raise HTTPException(status_code=403, detail={"code": "artifact_access_denied"}) from exc
    if "not_found" in str(exc):
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    if isinstance(exc, ArtifactIntegrityError):
        raise HTTPException(status_code=409, detail={"code": "artifact_integrity_failed"}) from exc
    raise HTTPException(status_code=503, detail={"code": "artifact_service_unavailable"}) from exc


@router.post("/uploads", status_code=201)
def create_upload(
    body: CreateUploadRequest,
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    identity = _identity(user, principal)
    granted = _granted_resources(user, identity)
    _assert_resources_allowed(body.resource_refs, granted)
    try:
        session = _service().create_upload(
            identity, media_type=body.media_type, expected_sha256=body.sha256,
            expected_byte_size=body.byte_size, resource_refs=body.resource_refs,
        )
    except ArtifactError as exc:
        _raise_artifact_error(exc)
    return {
        "upload_id": session.upload_id,
        "upload_url": f"/api/v2/capability-artifacts/uploads/{session.upload_id}/content",
        "expires_at": session.expires_at,
    }


@router.put("/uploads/{upload_id}/content", status_code=204)
async def upload_content(
    upload_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    identity = _identity(user, principal)
    try:
        service = _service()
        session = service.get_upload(upload_id, identity)
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > session.expected_byte_size:
                    raise ArtifactIntegrityError("uploaded object exceeds expected byte size")
                stream.write(chunk)
            stream.seek(0)
            service.upload_stream(upload_id, identity, stream)
    except ArtifactError as exc:
        _raise_artifact_error(exc)


@router.post("/uploads/{upload_id}:finalize")
def finalize_upload(
    upload_id: str,
    body: FinalizeUploadRequest,
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    try:
        ref = _service().finalize(upload_id, _identity(user, principal), reported_sha256=body.sha256)
    except ArtifactError as exc:
        _raise_artifact_error(exc)
    return {"artifact_ref": ref.model_dump(mode="json")}


@router.get("/{artifact_id}")
def get_artifact(
    artifact_id: str,
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    identity = _identity(user, principal)
    try:
        record = _service().authorize_download(
            artifact_id, identity, granted_resources=_granted_resources(user, identity)
        )
        from backend.core.ois_storage import generate_access_url
        url = generate_access_url(record.object_key, expire_in_seconds=300)
        if not url:
            raise ArtifactError("artifact_download_unavailable")
    except ArtifactError as exc:
        _raise_artifact_error(exc)
    return {"artifact_ref": record.artifact_ref.model_dump(mode="json"), "download_url": url}
