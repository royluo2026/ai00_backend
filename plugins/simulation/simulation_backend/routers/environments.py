"""REST compatibility routes that invoke Simulation only through Capability Gateway."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, IDENTITY_PATTERN, InvocationEnvelope, TenantIdentity
from backend.capability_v2.gateway import get_default_gateway
from backend.domain_ports.digital_model import ModelSnapshotRef
from backend.domain_ports.simulation import ExecutionPlanRef, ParameterSetRef, SimulationProfileRef
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user


router = APIRouter(prefix="/api/simulation/environments", tags=["simulation"])


class CreateEnvironmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    execution_plan_ref: ExecutionPlanRef
    model_snapshot_ref: ModelSnapshotRef
    parameter_set_ref: ParameterSetRef
    simulation_profile_ref: SimulationProfileRef
    confirmation_token: str | None = None


def _identity(user: dict, principal) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(**principal.model_dump()),
        tenant=TenantIdentity(
            tenant_id=str(user.get("team_id") or "default"), membership="member",
            active_roles=tuple(filter(None, (user.get("org_role"), user.get("system_role")))),
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )


def _correlation(value: str | None, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(IDENTITY_PATTERN, candidate) else fallback


async def _invoke(capability_id: str, payload: dict, request: Request, user: dict, principal, *, confirmation_token: str | None = None):
    gateway = get_default_gateway()
    request_id = _correlation(request.headers.get("X-Request-ID"), "cap_" + uuid.uuid4().hex)
    result = await gateway.invoke(InvocationEnvelope(
        capability_id=capability_id, major_version=1, catalog_release=gateway.catalog_release,
        payload=payload, identity=_identity(user, principal),
        idempotency_key=request.headers.get("Idempotency-Key"),
        approval_reference=confirmation_token, request_id=request_id,
        trace_id=_correlation(request.headers.get("X-Trace-ID"), request_id),
    ))
    return {"success": result.ok, "data": result.model_dump(mode="json")}


@router.post("")
async def create(body: CreateEnvironmentBody, request: Request, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal)):
    payload = body.model_dump(mode="json", exclude={"confirmation_token"})
    return await _invoke("simulation.environment.create", payload, request, user, principal, confirmation_token=body.confirmation_token)


@router.get("")
async def list_all(request: Request, limit: int = 50, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal)):
    return await _invoke("simulation.environment.search", {"limit": limit}, request, user, principal)


@router.get("/{environment_gid}")
async def get_one(environment_gid: str, request: Request, user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal)):
    return await _invoke("simulation.environment.get", {"environment_id": environment_gid}, request, user, principal)
