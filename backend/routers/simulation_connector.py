"""HTTP bootstrap adapter for Simulation-owned AI00 Connector pairing."""
from __future__ import annotations

from datetime import datetime, timezone
import tempfile

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.platform_sdk.auth import get_current_user
from plugins.simulation.simulation_backend.capabilities.connector_pairing import default_service
from plugins.simulation.simulation_backend.capabilities.connector_runtime import (
    ConnectorHealth, complete_connector_plan, get_leased_connector_plan,
    lease_connector_plan, record_connector_heartbeat,
)
from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository
from plugins.simulation.simulation_backend.domain.connector_pairing import PairingError, PairingRequest
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, TenantIdentity
from backend.capability_v2.operations import SqlOperationStore
from backend.contracts.connector_execution_plan_v1 import ConnectorPlanOutcomeV1, verify_connector_outcome
from backend.db.connection import get_conn


router = APIRouter(prefix="/api/v1/simulation/connectors", tags=["simulation-connector"])


class PairingApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class PairingCompleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: str = Field(min_length=1, max_length=191)
    verifier: str = Field(min_length=16, max_length=1024)


class ConnectorHeartbeatBody(ConnectorHealth):
    pass


class ConnectorLeaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_seconds: int = Field(default=60, ge=15, le=300)


class ConnectorCompleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: str = Field(min_length=1)
    outcome: ConnectorPlanOutcomeV1
    signature: str = Field(pattern="^hmac-sha256:[0-9a-f]{64}$")


def _error(exc: PairingError) -> HTTPException:
    code = str(exc)
    status = 404 if code == "pairing_not_found" else 409
    if code == "pairing_proof_invalid":
        status = 403
    return HTTPException(status_code=status, detail={"code": code})


def _feishu_user(user: dict = Depends(get_current_user)) -> dict:
    if not str(user.get("feishu_open_id") or "").strip():
        raise HTTPException(
            status_code=403,
            detail={"code": "feishu_login_required"},
        )
    return user


def _connector_auth(
    connector_id: str = Header(alias="X-AI00-Connector-ID"),
    connector_token: str = Header(alias="X-AI00-Connector-Token"),
) -> dict:
    try:
        row = SimulationConnectorRepository().authenticate_connector(connector_id, connector_token)
        return {**row, "gid": row["connector_id"], "_request_token": connector_token}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail="Invalid Connector credentials") from exc


@router.post("/pairings")
def request_pairing(body: PairingRequest):
    try:
        return {"success": True, "data": default_service.request(body).model_dump(mode="json")}
    except PairingError as exc:
        raise _error(exc) from exc


@router.get("/pairings/{user_code}")
def pairing_summary(user_code: str, user: dict = Depends(_feishu_user)):
    try:
        value = default_service.get_summary(user_code, user["gid"])
        return {"success": True, "data": value.model_dump(mode="json")}
    except PairingError as exc:
        raise _error(exc) from exc


@router.post("/pairings/{user_code}/approve")
def approve_pairing(
    user_code: str, body: PairingApproveBody,
    user: dict = Depends(_feishu_user),
):
    try:
        value = default_service.approve(
            user_code, user["gid"], str(user.get("team_id") or f"user:{user['gid']}"),
            expected_version=body.expected_version,
        )
        return {"success": True, "data": value.model_dump(mode="json")}
    except PairingError as exc:
        raise _error(exc) from exc


@router.post("/pairings/{pairing_id}/complete")
def complete_pairing(pairing_id: str, body: PairingCompleteBody):
    try:
        value = default_service.complete(pairing_id, body.installation_id, body.verifier)
        return {"success": True, "data": value.model_dump(mode="json")}
    except PairingError as exc:
        raise _error(exc) from exc


@router.get("/binding")
def connector_binding(user: dict = Depends(_feishu_user)):
    row = default_service.repository.binding_for_user(user["gid"])
    return {"success": True, "data": {
        "connector_id": row["connector_id"] if row else None,
        "installation_id": row["installation_id"] if row else None,
    }}


@router.post("/heartbeat")
def connector_heartbeat(body: ConnectorHeartbeatBody, connector: dict = Depends(_connector_auth)):
    try:
        record_connector_heartbeat(connector["gid"], connector["owner_user_gid"], body)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    return {"success": True}


@router.post("/plans/lease")
def connector_plan_lease(body: ConnectorLeaseBody, connector: dict = Depends(_connector_auth)):
    try:
        value = lease_connector_plan(connector["gid"], body.lease_seconds)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "connector_plan_lease_failed"}) from exc
    return {"success": True, "data": value}


@router.post("/plans/{plan_id}/complete")
async def connector_plan_complete(
    plan_id: str, body: ConnectorCompleteBody,
    connector: dict = Depends(_connector_auth),
):
    try:
        if not verify_connector_outcome(body.outcome, body.signature, connector["_request_token"]):
            raise PermissionError("invalid_outcome_signature")
        await complete_connector_plan(connector["gid"], plan_id, body.lease_id, body.outcome)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    return {"success": True}


def _plan_artifact(plan, artifact_id: str):
    def visit(value):
        if isinstance(value, dict):
            candidate = value.get("artifact_ref")
            if isinstance(candidate, dict) and candidate.get("artifact_id") == artifact_id:
                return candidate
            for child in value.values():
                found = visit(child)
                if found:
                    return found
        elif isinstance(value, (list, tuple)):
            for child in value:
                found = visit(child)
                if found:
                    return found
        return None

    return visit(plan.model_dump(mode="json"))


@router.get("/plans/{plan_id}/artifacts/{artifact_id}")
def connector_plan_artifact(
    plan_id: str, artifact_id: str, lease_id: str = Query(min_length=1),
    connector: dict = Depends(_connector_auth),
):
    try:
        plan = get_leased_connector_plan(connector["gid"], plan_id, lease_id)
        expected = _plan_artifact(plan, artifact_id)
        if expected is None:
            raise PermissionError("artifact_not_bound_to_plan")
        from backend.capability_v2.artifacts import SqlArtifactStore
        record = SqlArtifactStore(get_conn).get_artifact(artifact_id)
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


@router.put("/plans/{plan_id}/steps/{step_id}/result-artifact")
async def connector_step_result_artifact(
    plan_id: str, step_id: str, request: Request,
    lease_id: str = Query(min_length=1),
    content_sha256: str = Header(alias="X-AI00-Content-SHA256", pattern="^[0-9a-f]{64}$"),
    content_length: int = Header(alias="X-AI00-Content-Length", ge=0, le=100 * 1024 * 1024),
    media_type: str = Header(default="image/png", alias="X-AI00-Media-Type"),
    connector: dict = Depends(_connector_auth),
):
    try:
        plan = get_leased_connector_plan(connector["gid"], plan_id, lease_id)
        step = next((item for item in plan.steps if item.step_id == step_id), None)
        if step is None:
            raise PermissionError("plan_step_not_found")
        refs = step.payload.get("artifact_resource_refs", ())
        if not isinstance(refs, (list, tuple)) or any(not isinstance(item, str) for item in refs):
            raise ValueError("artifact_resource_refs_invalid")
        identity = ConsumerIdentity(
            actor=ActorIdentity(user_id=plan.user_id, authentication_method="connector-delegated", authenticated_at=datetime.now(timezone.utc)),
            tenant=TenantIdentity(tenant_id=plan.tenant_id, membership="connector"),
            consumer=ConsumerDescriptor(type=ConsumerType.LOCAL_RUNTIME, consumer_id=connector["gid"]),
        )
        from backend.capability_v2.artifacts import ArtifactIntegrityError, ArtifactService, OisObjectStorage, SqlArtifactStore
        service = ArtifactService(SqlArtifactStore(get_conn), OisObjectStorage())
        session = service.create_upload(
            identity, media_type=media_type, expected_sha256=content_sha256,
            expected_byte_size=content_length, resource_refs=tuple(refs),
        )
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
            size = 0
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
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "artifact_upload_failed"}) from exc


__all__ = ["router"]
