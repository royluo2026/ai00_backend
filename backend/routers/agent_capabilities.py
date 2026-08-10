"""Trusted HTTP adapter for run-scoped Agent capability delegations."""
from __future__ import annotations

import hmac
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.capability_v2.contracts import (
    ActorIdentity, AutomationLevel, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    DelegationContext, InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.delegation import DelegationError, DelegationGrant, SqlDelegationStore, issue_delegation
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.policies import GatewayPolicyError
from backend.db.connection import get_conn
from backend.routers.deps import build_capability_authorization_grants, build_profile, get_authenticated_principal, get_current_user
from backend.services import user_service

router = APIRouter(prefix="/api/v2/agent-capabilities", tags=["agent-capabilities"])


class DelegationExchangeRequest(BaseModel):
    run_id: str = Field(pattern=r"^run_[A-Za-z0-9_-]{8,128}$")
    catalog_release: str = Field(pattern=r"^rel_[0-9a-f]{32}$")
    capability_scopes: tuple[str, ...] = Field(min_length=1, max_length=64)
    resource_scopes: tuple[str, ...] = Field(min_length=1, max_length=128)
    data_scopes: tuple[str, ...] = Field(default=("internal",), min_length=1, max_length=8)
    maximum_automation_level: AutomationLevel = AutomationLevel.A2
    ttl_seconds: int = Field(default=3600, ge=60, le=28800)


class AgentInvokeRequest(BaseModel):
    major_version: int = Field(ge=1)
    catalog_release: str = Field(pattern=r"^rel_[0-9a-f]{32}$")
    payload: dict[str, Any] = Field(default_factory=dict)
    approval_reference: str | None = Field(default=None, max_length=512)


def _require_service(value: str | None) -> None:
    configured = os.getenv("AGENT_RUNTIME_SERVICE_TOKEN", "").strip()
    if len(configured) < 32:
        raise HTTPException(status_code=503, detail={"code": "agent_service_not_configured"})
    if not value or not hmac.compare_digest(configured, value):
        raise HTTPException(status_code=401, detail={"code": "agent_service_authentication_failed"})


def _consume_identity(service_credential: str | None, delegation_token: str | None) -> tuple[ConsumerIdentity, dict]:
    _require_service(service_credential)
    if not delegation_token:
        raise HTTPException(status_code=401, detail={"code": "delegation_required"})
    try:
        grant = SqlDelegationStore(get_conn).consume_active(delegation_token)
    except DelegationError as exc:
        raise HTTPException(status_code=401, detail={"code": str(exc)}) from exc
    if grant.consumer_type is not ConsumerType.AGENT or not grant.agent_run_id or not grant.user_id:
        raise HTTPException(status_code=403, detail={"code": "agent_delegation_required"})
    user = user_service.get_by_gid(grant.user_id)
    if not user or str(user.get("team_id") or "default") != grant.tenant_id:
        raise HTTPException(status_code=403, detail={"code": "delegated_membership_inactive"})
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            user_id=grant.user_id, authentication_method=grant.authentication_method,
            authenticated_at=grant.authenticated_at,
        ),
        tenant=TenantIdentity(
            tenant_id=grant.tenant_id, membership="member",
            active_roles=tuple(filter(None, (user.get("org_role"), user.get("system_role")))),
        ),
        consumer=ConsumerDescriptor(
            type=ConsumerType.AGENT, consumer_id=grant.consumer_id,
            consumer_version=grant.consumer_version, agent_run_id=grant.agent_run_id,
        ),
        delegation=DelegationContext(
            delegation_id=grant.delegation_id, delegated_by=grant.delegated_by,
            capability_scopes=grant.capability_scopes, resource_scopes=grant.resource_scopes,
            data_scopes=grant.data_scopes, catalog_release=grant.catalog_release,
            maximum_automation_level=grant.maximum_automation_level, expires_at=grant.expires_at,
        ),
    )
    return identity, user


def _agent_descriptors_for_user(current_user: dict):
    tenant_id = str(current_user.get("team_id") or "default")
    grants = build_capability_authorization_grants(current_user, tenant_id, "web")
    permissions = set(build_profile(current_user).get("permissions", ()))
    descriptors = []
    for item in get_default_gateway().catalog().descriptors:
        if not item.exposure.agent:
            continue
        if item.data_classification not in grants.data_scopes and "*" not in grants.data_scopes:
            continue
        if item.authorization_policy.startswith("legacy:"):
            required = set(filter(None, item.authorization_policy.removeprefix("legacy:").split(",")))
            if required != {"authenticated"} and not required <= permissions:
                continue
        descriptors.append(item)
    return tuple(descriptors)


@router.post("/delegations")
def exchange_delegation(
    body: DelegationExchangeRequest,
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    service_credential: str | None = Header(default=None, alias="X-AI00-Service-Credential"),
):
    _require_service(service_credential)
    gateway = get_default_gateway()
    if body.catalog_release != gateway.catalog_release:
        raise HTTPException(status_code=409, detail={"code": "catalog_release_not_active"})
    descriptors = {(item.id, item.major_version): item for item in _agent_descriptors_for_user(current_user)}
    invalid = [scope for scope in body.capability_scopes if not any(
        item.id == scope for item in descriptors.values()
    )]
    if invalid:
        raise HTTPException(status_code=403, detail={"code": "agent_capability_scope_denied", "scopes": invalid})
    tenant_id = str(current_user.get("team_id") or "default")
    actor_grants = build_capability_authorization_grants(current_user, tenant_id, "web")
    if any(scope not in actor_grants.resource_scopes and "*" not in actor_grants.resource_scopes for scope in body.resource_scopes):
        raise HTTPException(status_code=403, detail={"code": "resource_scope_denied"})
    if any(scope not in actor_grants.data_scopes and "*" not in actor_grants.data_scopes for scope in body.data_scopes):
        raise HTTPException(status_code=403, detail={"code": "data_scope_denied"})
    now = datetime.now(UTC)
    authentication_deadline = principal.authenticated_at + timedelta(hours=8)
    if authentication_deadline <= now:
        raise HTTPException(status_code=401, detail={"code": "authentication_freshness_required"})
    grant = DelegationGrant(
        delegation_id=f"dlg_{uuid.uuid4().hex}", delegated_by=str(current_user["gid"]),
        user_id=str(current_user["gid"]), tenant_id=tenant_id, consumer_type=ConsumerType.AGENT,
        consumer_id="ai00.agent-runtime", consumer_version="2", agent_run_id=body.run_id,
        catalog_release=body.catalog_release, capability_scopes=body.capability_scopes,
        resource_scopes=body.resource_scopes, data_scopes=body.data_scopes,
        maximum_automation_level=body.maximum_automation_level,
        authentication_method=principal.authentication_method, authenticated_at=principal.authenticated_at,
        expires_at=min(now + timedelta(seconds=body.ttl_seconds), authentication_deadline),
    )
    issued = issue_delegation(SqlDelegationStore(get_conn), grant)
    return {"delegation_id": grant.delegation_id, "delegation_token": issued.token,
            "catalog_release": grant.catalog_release, "expires_at": grant.expires_at.isoformat()}


@router.get("/catalog-preview")
def catalog_preview(
    _current_user: dict = Depends(get_current_user),
    service_credential: str | None = Header(default=None, alias="X-AI00-Service-Credential"),
):
    _require_service(service_credential)
    catalog = get_default_gateway().catalog()
    allowed = {(item.id, item.major_version) for item in _agent_descriptors_for_user(_current_user)}
    return {"release_id": catalog.release_id, "descriptors": [
        item.model_dump(mode="json") for item in catalog.descriptors if (item.id, item.major_version) in allowed
    ]}


@router.get("/catalog")
def delegated_catalog(
    release: str = Query(pattern=r"^rel_[0-9a-f]{32}$"),
    service_credential: str | None = Header(default=None, alias="X-AI00-Service-Credential"),
    delegation_token: str | None = Header(default=None, alias="X-AI00-Delegation"),
):
    identity, _user = _consume_identity(service_credential, delegation_token)
    if identity.delegation is None or identity.delegation.catalog_release != release:
        raise HTTPException(status_code=409, detail={"code": "delegation_catalog_mismatch"})
    catalog = get_default_gateway().catalog(release)
    scopes = set(identity.delegation.capability_scopes)
    descriptors = [item.model_dump(mode="json") for item in catalog.descriptors if item.exposure.agent and (item.id in scopes or "*" in scopes)]
    return {"release_id": release, "descriptors": descriptors}


async def _envelope(capability_id: str, body: AgentInvokeRequest, request: Request,
                    service_credential: str | None, delegation_token: str | None) -> InvocationEnvelope:
    identity, _user = _consume_identity(service_credential, delegation_token)
    request_id = request.headers.get("X-Request-ID") or f"agent_{uuid.uuid4().hex}"
    if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$", request_id):
        raise HTTPException(status_code=400, detail={"code": "invalid_request_id"})
    return InvocationEnvelope(
        capability_id=capability_id, major_version=body.major_version,
        catalog_release=body.catalog_release, payload=body.payload, identity=identity,
        approval_reference=body.approval_reference, request_id=request_id, trace_id=request_id,
    )


@router.post("/{capability_id}:invoke")
async def delegated_invoke(capability_id: str, body: AgentInvokeRequest, request: Request,
    service_credential: str | None = Header(default=None, alias="X-AI00-Service-Credential"),
    delegation_token: str | None = Header(default=None, alias="X-AI00-Delegation")):
    result = await get_default_gateway().invoke(await _envelope(
        capability_id, body, request, service_credential, delegation_token))
    return result.model_dump(mode="json")


@router.post("/{capability_id}:confirm")
async def delegated_confirm(capability_id: str, body: AgentInvokeRequest, request: Request,
    service_credential: str | None = Header(default=None, alias="X-AI00-Service-Credential"),
    delegation_token: str | None = Header(default=None, alias="X-AI00-Delegation")):
    try:
        issued = await get_default_gateway().request_approval(await _envelope(
            capability_id, body, request, service_credential, delegation_token))
    except GatewayPolicyError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": exc.message}) from exc
    return {"approval_reference": issued.token, "approval_id": issued.challenge.approval_id,
            "expires_at": issued.challenge.expires_at.isoformat()}
