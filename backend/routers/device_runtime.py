"""User and device HTTP adapters for the Local Runtime control plane."""
from __future__ import annotations

from datetime import datetime, timezone
import tempfile

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from plugins.device.device_backend.public import (
    activate_device, authorize_active_lease, authorize_command_artifact, authenticate_device, complete_command, create_enrollment,
    heartbeat, lease_command, list_devices, mark_command_reconciled, pending_reconciliations, revoke_device,
)
from backend.platform_sdk.auth import build_profile, get_current_user
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, OperationStatus, TenantIdentity
from backend.capability_v2.operations import SqlOperationStore, TrustedExternalOperationReconciler
from backend.db.connection import get_conn
from backend.domain_ports.local_integration import LocalOperationOutcome, verify_operation_outcome

router = APIRouter(prefix="/api/v1", tags=["device-runtime"])

class EnrollmentBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    team_gid: str | None = None
    ttl_minutes: int = Field(default=30, ge=5, le=1440)
class ActivateBody(BaseModel):
    enrollment_token: str = Field(min_length=20)
    runtime_version: str = Field(default="", max_length=64)
    capabilities: list[str] = Field(default_factory=list, max_length=128)
class RuntimeStateBody(BaseModel):
    runtime_version: str = Field(default="", max_length=64)
    capabilities: list[str] = Field(default_factory=list, max_length=128)
class LeaseBody(BaseModel):
    lease_seconds: int = Field(default=60, ge=15, le=300)
class CompleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: str = Field(min_length=1)
    outcome: LocalOperationOutcome
    signature: str = Field(pattern="^hmac-sha256:[0-9a-f]{64}$")

def _device_auth(device_gid: str = Header(alias="X-AI00-Device-ID"), device_token: str = Header(alias="X-AI00-Device-Token")) -> dict:
    try:
        return {**authenticate_device(device_gid, device_token), "_request_token": device_token}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail="Invalid device credentials") from exc


def _operation_reconciler() -> TrustedExternalOperationReconciler:
    return TrustedExternalOperationReconciler(SqlOperationStore(get_conn), allowed_kind_prefix="vismockup.")


def _reconcile_pending(device_gid: str) -> None:
    reconciler = _operation_reconciler()
    targets = {
        "pending_completed": OperationStatus.COMPLETED,
        "pending_failed": OperationStatus.FAILED,
        "pending_outcome_unknown": OperationStatus.OUTCOME_UNKNOWN,
    }
    for item in pending_reconciliations(device_gid):
        reconciler.reconcile(item["gid"], targets[item["status"]], error_code=item.get("error") or None)
        mark_command_reconciled(device_gid, item["gid"], item["status"])

@router.post("/devices/enrollments")
def enroll(body: EnrollmentBody, user: dict = Depends(get_current_user)):
    permissions = set(build_profile(user).get("permissions", []))
    if "system.tech_config" not in permissions:
        raise HTTPException(status_code=403, detail="Missing permission: system.tech_config")
    if body.team_gid is not None and body.team_gid != user.get("team_id"):
        raise HTTPException(status_code=403, detail="Device team must match the active tenant")
    return {"success": True, "data": create_enrollment(user, body.display_name, body.team_gid, body.ttl_minutes)}

@router.get("/devices")
def devices(user: dict = Depends(get_current_user)):
    return {"success": True, "data": list_devices(user["gid"], user.get("team_id"))}

@router.delete("/devices/{device_gid}")
def revoke(device_gid: str, user: dict = Depends(get_current_user)):
    try:
        revoke_device(user["gid"], device_gid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True}
@router.post("/device-runtime/activate")
def activate(body: ActivateBody):
    try:
        return {"success": True, "data": activate_device(body.enrollment_token, body.runtime_version, body.capabilities)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/device-runtime/heartbeat")
def runtime_heartbeat(body: RuntimeStateBody, device: dict = Depends(_device_auth)):
    heartbeat(device["gid"], body.runtime_version, body.capabilities)
    return {"success": True}

@router.post("/connector/activate")
def connector_activate(body: ActivateBody):
    raise HTTPException(status_code=410, detail={
        "code": "connector_browser_pairing_required",
        "replacement": "/api/v1/simulation/connectors/pairings",
    })

@router.post("/device-runtime/commands/lease")
def runtime_lease(body: LeaseBody, device: dict = Depends(_device_auth)):
    try:
        _reconcile_pending(device["gid"])
        lease = lease_command(device["gid"], body.lease_seconds)
        _reconcile_pending(device["gid"])
        if lease is not None:
            _operation_reconciler().reconcile(lease["operation"]["operation_id"], OperationStatus.CLAIMED)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "operation_reconciliation_unavailable"}) from exc
    return {"success": True, "data": lease}

@router.post("/device-runtime/commands/{command_gid}/complete")
def runtime_complete(command_gid: str, body: CompleteBody, device: dict = Depends(_device_auth)):
    try:
        if body.outcome.operation_id != command_gid or not verify_operation_outcome(body.outcome, body.signature, device["_request_token"]):
            raise PermissionError("invalid_outcome_signature")
        complete_command(device["gid"], command_gid, body.lease_id, body.outcome.status, body.outcome.result, body.outcome.error_code)
        _reconcile_pending(device["gid"])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "operation_reconciliation_unavailable"}) from exc
    return {"success": True}


@router.get("/device-runtime/commands/{command_gid}/artifacts/{artifact_id}")
def runtime_artifact(
    command_gid: str,
    artifact_id: str,
    lease_id: str = Query(min_length=1),
    device: dict = Depends(_device_auth),
):
    try:
        expected = authorize_command_artifact(device["gid"], command_gid, lease_id, artifact_id)
        from backend.capability_v2.artifacts import SqlArtifactStore
        from backend.db.connection import get_conn
        record = SqlArtifactStore(get_conn).get_artifact(artifact_id)
        operation = SqlOperationStore(get_conn).get(command_gid)
        if record.tenant_id != operation.tenant_id or f"artifact:{artifact_id}" not in operation.resource_refs:
            raise PermissionError("artifact_not_authorized_for_operation")
        if record.artifact_ref.model_dump(mode="json") != expected:
            raise ValueError("artifact_ref_mismatch")
        from backend.core.ois_storage import generate_access_url
        url = generate_access_url(record.object_key, expire_in_seconds=120)
        if not url:
            raise RuntimeError("artifact_download_unavailable")
        return {"success": True, "data": {"artifact_ref": expected, "download_url": url}}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "artifact_download_unavailable"}) from exc


@router.put("/device-runtime/commands/{command_gid}/result-artifact")
async def runtime_result_artifact(
    command_gid: str,
    request: Request,
    lease_id: str = Query(min_length=1),
    content_sha256: str = Header(alias="X-AI00-Content-SHA256", pattern="^[0-9a-f]{64}$"),
    content_length: int = Header(alias="X-AI00-Content-Length", ge=0, le=100 * 1024 * 1024),
    device: dict = Depends(_device_auth),
):
    try:
        authorize_active_lease(device["gid"], command_gid, lease_id, "vismockup.capture")
        store = SqlOperationStore(get_conn)
        operation = store.get(command_gid)
        identity = ConsumerIdentity(
            actor=ActorIdentity(user_id=operation.actor_id, authentication_method="device-delegated", authenticated_at=datetime.now(timezone.utc)),
            tenant=TenantIdentity(tenant_id=operation.tenant_id, membership="device"),
            consumer=ConsumerDescriptor(type=ConsumerType.LOCAL_RUNTIME, consumer_id=device["gid"]),
        )
        from backend.capability_v2.artifacts import ArtifactIntegrityError, ArtifactService, OisObjectStorage, SqlArtifactStore
        service = ArtifactService(SqlArtifactStore(get_conn), OisObjectStorage())
        session = service.create_upload(
            identity, media_type="image/png", expected_sha256=content_sha256,
            expected_byte_size=content_length, resource_refs=operation.resource_refs,
        )
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > content_length:
                    raise ArtifactIntegrityError("uploaded object exceeds expected byte size")
                stream.write(chunk)
            stream.seek(0)
            service.upload_stream(session.upload_id, identity, stream)
        ref = service.finalize(session.upload_id, identity, reported_sha256=content_sha256)
        return {"success": True, "data": {"artifact_ref": ref.model_dump(mode="json")}}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "artifact_upload_failed"}) from exc
