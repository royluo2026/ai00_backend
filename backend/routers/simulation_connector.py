"""HTTP bootstrap adapter for Simulation-owned AI00 Connector pairing."""
from __future__ import annotations

from typing import Literal
from backend.contracts.connector_execution_plan_v2 import ConnectorPlanOutcomeV2, IDENTITY_PATTERN
from plugins.simulation.simulation_backend.application.connector_runtime_sessions import runtime_session_service
from plugins.simulation.simulation_backend.capabilities.connector_pairing import app_pairing_service
from plugins.simulation.simulation_backend.domain.connector_pairing import PairingError
from plugins.simulation.simulation_backend.data.connector_repository import ConnectorRepositoryError

from datetime import datetime, timezone
import hashlib
import tempfile
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from plugins.simulation.simulation_backend.capabilities.connector_runtime import (
    ConnectorHealth, complete_connector_plan, get_leased_connector_plan,
    lease_connector_plan, record_connector_heartbeat,
)
from plugins.simulation.simulation_backend.data.connector_repository import SimulationConnectorRepository
from plugins.simulation.simulation_backend.application.connector_wakeup import connector_wake_broker
from plugins.simulation.simulation_backend.domain.connector_pairing import PairingRequest
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, InvocationEnvelope, TenantIdentity
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.web_compatibility import build_trusted_web_envelope, invoke_trusted_web_compatibility
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


class PairingActivateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_id: str = Field(min_length=1, max_length=191)
    activation_proof: str = Field(min_length=16, max_length=1024)


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


def _gateway_data(result):
    if result.ok:
        return {"success": True, "data": result.data}
    code = result.error.code if result.error else "capability_unavailable"
    if code in {"pairing_proof_invalid", "pairing_activation_proof_invalid", "permission_denied"}:
        status = 403
    elif code in {"pairing_not_found", "pairing_bootstrap_not_found"}:
        status = 404
    elif code in {"pairing_expired", "pairing_bootstrap_expired"}:
        status = 410
    elif code in {"invalid_input"}:
        status = 400
    elif code in {
        "catalog_resolution_failed", "provider_failed", "reliability_unavailable",
        "reliability_failed", "authorization_failed",
    }:
        status = 503
    else:
        status = 409
    raise HTTPException(status_code=status, detail={"code": code})


def _request_id(request: Request) -> str:
    candidate = str(request.headers.get("X-Request-ID") or "").strip()
    return candidate if candidate and candidate.replace("-", "").replace("_", "").isalnum() else f"connector_{uuid.uuid4().hex}"


def _bootstrap_identity(installation_id: str) -> ConsumerIdentity:
    installation_ref = "install_" + hashlib.sha256(installation_id.encode("utf-8")).hexdigest()[:32]
    return ConsumerIdentity(
        actor=ActorIdentity(
            service_id="ai00.connector.bootstrap", authentication_method="connector_bootstrap",
            authenticated_at=datetime.now(timezone.utc),
        ),
        tenant=TenantIdentity(tenant_id="connector_bootstrap", membership="bootstrap"),
        consumer=ConsumerDescriptor(
            type=ConsumerType.LOCAL_RUNTIME, consumer_id="ai00.connector.bootstrap",
            installation_id=installation_ref,
        ),
    )


async def _invoke_local(capability_id: str, payload: dict, request: Request, installation_id: str, gateway):
    request_id = _request_id(request)
    result = await gateway.invoke(InvocationEnvelope(
        capability_id=capability_id, major_version=1, catalog_release=gateway.catalog_release,
        payload=payload, identity=_bootstrap_identity(installation_id),
        request_id=request_id, trace_id=request_id,
        idempotency_key=request.headers.get("Idempotency-Key") or request_id,
    ))
    return _gateway_data(result)


async def _invoke_web(capability_id: str, payload: dict, request: Request, user: dict, principal, gateway):
    request_id = _request_id(request)
    result = await invoke_trusted_web_compatibility(gateway, build_trusted_web_envelope(
        gateway, capability_id=capability_id, payload=payload,
        current_user=user, principal=principal, consumer_id="ai00.web.simulation",
        request_id=request_id, trace_id=request_id,
        idempotency_key=request.headers.get("Idempotency-Key") or request_id,
    ))
    return _gateway_data(result)


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
async def request_pairing(
    body: PairingRequest, request: Request, gateway=Depends(get_default_gateway),
):
    return await _invoke_local(
        "simulation.connector.pairing.request", body.model_dump(mode="json"),
        request, body.installation_id, gateway,
    )


@router.get("/pairings/{user_code}")
async def pairing_summary(
    user_code: str, request: Request, user: dict = Depends(_feishu_user),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    return await _invoke_web(
        "simulation.connector.pairing.summary.get", {"user_code": user_code},
        request, user, principal, gateway,
    )


@router.post("/pairings/{user_code}/approve")
async def approve_pairing(
    user_code: str, body: PairingApproveBody, request: Request,
    user: dict = Depends(_feishu_user),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    return await _invoke_web(
        "simulation.connector.pairing.approve",
        {"user_code": user_code, "expected_version": body.expected_version},
        request, user, principal, gateway,
    )


@router.post("/pairings/{pairing_id}/complete")
async def complete_pairing(
    pairing_id: str, body: PairingCompleteBody, request: Request,
    gateway=Depends(get_default_gateway),
):
    return await _invoke_local(
        "simulation.connector.pairing.complete",
        {"pairing_id": pairing_id, **body.model_dump(mode="json")},
        request, body.installation_id, gateway,
    )


@router.post("/pairings/{pairing_id}/activate")
async def activate_pairing(
    pairing_id: str, body: PairingActivateBody, request: Request,
    gateway=Depends(get_default_gateway),
):
    return await _invoke_local(
        "simulation.connector.pairing.activate",
        {"pairing_id": pairing_id, **body.model_dump(mode="json")},
        request, body.connector_id, gateway,
    )


@router.get("/binding")
async def connector_binding(
    request: Request, user: dict = Depends(_feishu_user),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    return await _invoke_web(
        "simulation.connector.binding.get", {}, request, user, principal, gateway,
    )


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


@router.websocket("/plans/wake")
async def connector_plan_wake(
    websocket: WebSocket, connector: dict = Depends(_connector_auth),
):
    """Wake-only channel; plans still require the authenticated lease endpoint."""
    await websocket.accept()
    try:
        async with connector_wake_broker.subscribe(connector["gid"]) as subscription:
            await websocket.send_json({"type": "ready"})
            while True:
                signaled = await subscription.wait(25)
                await websocket.send_json({
                    "type": "plan_available" if signaled else "keepalive",
                })
    except WebSocketDisconnect:
        return


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
        from backend.capability_v2.artifacts import FilesystemObjectStorage, configured_object_storage
        storage = configured_object_storage()
        if isinstance(storage, FilesystemObjectStorage):
            url = (
                f"/api/v1/simulation/connectors/plans/{plan_id}/artifacts/{artifact_id}/content"
                f"?lease_id={lease_id}&connector_id={connector['gid']}"
            )
        else:
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


@router.get("/plans/{plan_id}/artifacts/{artifact_id}/content")
def connector_plan_artifact_content(
    plan_id: str, artifact_id: str, lease_id: str = Query(min_length=1),
    connector_id: str = Query(min_length=1),
):
    """Serve a lease-scoped local artifact like a short-lived presigned URL."""
    try:
        plan = get_leased_connector_plan(connector_id, plan_id, lease_id)
        expected = _plan_artifact(plan, artifact_id)
        if expected is None:
            raise PermissionError("artifact_not_bound_to_plan")
        from backend.capability_v2.artifacts import FilesystemObjectStorage, SqlArtifactStore, configured_object_storage
        record = SqlArtifactStore(get_conn).get_artifact(artifact_id)
        if record.artifact_ref.model_dump(mode="json") != expected:
            raise ValueError("artifact_ref_mismatch")
        storage = configured_object_storage()
        if not isinstance(storage, FilesystemObjectStorage):
            raise RuntimeError("local_artifact_transport_disabled")
        from fastapi.responses import FileResponse
        return FileResponse(storage.path_for(record.object_key), media_type=record.artifact_ref.media_type)
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
        from backend.capability_v2.artifacts import ArtifactIntegrityError, ArtifactService, SqlArtifactStore, configured_object_storage
        service = ArtifactService(SqlArtifactStore(get_conn), configured_object_storage())
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

# V2 device/control-plane transport. User intent (approval and takeover) stays
# behind the Capability gateway; no user-authenticated token issuance route.


class AppPairingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    device_signing_jwk: dict
    bootstrap_encryption_jwk: dict
    nonce: str = Field(min_length=16, max_length=512)


class AppPairingActivate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    signing_challenge: str = Field(min_length=1, max_length=1024)
    signature: str = Field(pattern=r'^[A-Za-z0-9_-]{86}$')
    decrypted_challenge: str = Field(min_length=16, max_length=512)


class RuntimeChallengeBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    device_id: str = Field(pattern=IDENTITY_PATTERN)
    generation: int = Field(ge=1)
    runtime_instance_id: str = Field(pattern=IDENTITY_PATTERN)
    runtime_type: Literal['electron']
    plan_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)


class RuntimeRegisterBody(RuntimeChallengeBody):
    challenge: str = Field(min_length=1, max_length=1024)
    signature: str = Field(pattern=r'^[A-Za-z0-9_-]{86}$')


def _transport(call):
    try:
        return {'success': True, 'data': call()}
    except (PairingError, ConnectorRepositoryError) as exc:
        code = str(exc)
        status = 401 if code in {'runtime_session_invalid', 'device_credential_invalid', 'runtime_proof_invalid', 'runtime_type_invalid'} else 409
        raise HTTPException(status_code=status, detail={'code': code}) from exc


def _runtime_pins(
    device_id: str = Header(alias='X-AI00-Device-ID', pattern=IDENTITY_PATTERN),
    generation: int = Header(alias='X-AI00-Runtime-Generation', ge=1),
    runtime_instance_id: str = Header(alias='X-AI00-Runtime-Instance-ID', pattern=IDENTITY_PATTERN),
    runtime_type: Literal['electron'] = Header(alias='X-AI00-Runtime-Type'),
    session_token: str = Header(alias='X-AI00-Runtime-Session', min_length=1, max_length=512),
):
    return dict(device_id=device_id, generation=generation, runtime_instance_id=runtime_instance_id,
                runtime_type=runtime_type, token=session_token)


def _runtime_auth(pins: dict = Depends(_runtime_pins)):
    _transport(lambda: runtime_session_service.authenticate(**pins))
    return pins


def _reconciliation_auth(plan_id: str, pins: dict = Depends(_runtime_pins)):
    _transport(lambda: runtime_session_service.authenticate_reconciliation(plan_id=plan_id, **pins))
    return pins


@router.post('/v2/pairings')
def app_pairing_request(body: AppPairingRequest):
    return _transport(lambda: app_pairing_service.request_v2(body.device_signing_jwk, body.bootstrap_encryption_jwk, body.nonce))


@router.post('/v2/pairings/{pairing_id}/activate')
def app_pairing_activate(pairing_id: str, body: AppPairingActivate):
    return _transport(lambda: app_pairing_service.activate_v2(pairing_id, body.signing_challenge, body.signature, body.decrypted_challenge))


@router.post('/v2/runtime/challenge')
def runtime_challenge(body: RuntimeChallengeBody, device_credential: str = Header(alias='X-AI00-Device-Credential', min_length=1, max_length=512)):
    return _transport(lambda: runtime_session_service.challenge(device_credential=device_credential, **body.model_dump()))


@router.post('/v2/runtime/register')
def runtime_register(body: RuntimeRegisterBody, device_credential: str = Header(alias='X-AI00-Device-Credential', min_length=1, max_length=512)):
    if body.plan_id is not None:
        raise HTTPException(status_code=400, detail={'code': 'runtime_scope_invalid'})
    from dataclasses import asdict
    return _transport(lambda: asdict(runtime_session_service.register(device_credential=device_credential, **body.model_dump(exclude={'plan_id'}))))


@router.post('/v2/runtime/reconciliation/register')
def runtime_reconciliation_register(body: RuntimeRegisterBody, device_credential: str = Header(alias='X-AI00-Device-Credential', min_length=1, max_length=512)):
    if not body.plan_id:
        raise HTTPException(status_code=400, detail={'code': 'plan_reconciliation_invalid'})
    return _transport(lambda: runtime_session_service.register_reconciliation(device_credential=device_credential, **body.model_dump()))


@router.post('/v2/heartbeat')
def runtime_heartbeat(pins: dict = Depends(_runtime_auth)):
    return _transport(lambda: runtime_session_service.heartbeat(**pins))


@router.post('/v2/runtime/renew')
def runtime_renew(pins: dict = Depends(_runtime_auth)):
    return _transport(lambda: runtime_session_service.renew(**pins))


@router.post('/v2/plans/lease')
def runtime_lease(body: ConnectorLeaseBody, pins: dict = Depends(_runtime_auth)):
    return _transport(lambda: runtime_session_service.lease(**pins, lease_seconds=body.lease_seconds))


@router.websocket('/v2/plans/wake')
async def runtime_wake(websocket: WebSocket, pins: dict = Depends(_runtime_pins)):
    try:
        runtime_session_service.authenticate(**pins)
        await websocket.accept()
        async with connector_wake_broker.subscribe(pins['device_id']) as subscription:
            await websocket.send_json({'type': 'ready'})
            while True:
                signaled = await subscription.wait(25)
                runtime_session_service.authenticate(**pins)
                await websocket.send_json({'type': 'plan_available' if signaled else 'keepalive'})
    except ConnectorRepositoryError:
        await websocket.close(code=4401)
    except WebSocketDisconnect:
        return


@router.post('/v2/plans/{plan_id}/outcome')
def runtime_outcome(plan_id: str, body: ConnectorPlanOutcomeV2, pins: dict = Depends(_runtime_auth)):
    if plan_id != body.plan_id:
        raise HTTPException(status_code=409, detail={'code': 'plan_identity_mismatch'})
    return _transport(lambda: runtime_session_service.outcome(outcome=body, **pins))


@router.get('/v2/plans/{plan_id}/probe')
def runtime_probe(plan_id: str, pins: dict = Depends(_reconciliation_auth)):
    return _transport(lambda: runtime_session_service.probe(plan_id=plan_id, **pins))


@router.post('/v2/plans/{plan_id}/reconcile')
def runtime_reconcile(plan_id: str, body: ConnectorPlanOutcomeV2, pins: dict = Depends(_reconciliation_auth)):
    if plan_id != body.plan_id:
        raise HTTPException(status_code=409, detail={'code': 'plan_identity_mismatch'})
    return _transport(lambda: runtime_session_service.outcome(outcome=body, reconcile=True, **pins))


__all__ = ["router"]
