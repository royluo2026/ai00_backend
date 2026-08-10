"""Trusted MCP adapter: external auth is exchanged for a scoped delegation."""
from __future__ import annotations

import hmac
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.capability_v2.contracts import (
    ActorIdentity, AutomationLevel, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    DelegationContext, InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.delegation import DelegationError, DelegationGrant, SqlDelegationStore, issue_delegation
from backend.capability_v2.gateway import get_default_gateway
from backend.db.connection import get_conn
from backend.routers.deps import build_capability_authorization_grants, build_profile, get_authenticated_principal, get_current_user
from backend.services import user_service

router = APIRouter(prefix="/api/v2/mcp-capabilities", tags=["mcp-capabilities"])


class McpInvokeRequest(BaseModel):
    major_version: int = Field(ge=1)
    catalog_release: str = Field(pattern=r"^rel_[0-9a-f]{32}$")
    payload: dict[str, Any] = Field(default_factory=dict)


def _require_service(value: str | None) -> None:
    configured = os.getenv("MCP_GATEWAY_SERVICE_TOKEN", "").strip()
    if len(configured) < 32:
        raise HTTPException(status_code=503, detail={"code": "mcp_service_not_configured"})
    if not value or not hmac.compare_digest(configured, value):
        raise HTTPException(status_code=401, detail={"code": "mcp_service_authentication_failed"})


def _mcp_descriptors():
    return tuple(item for item in get_default_gateway().catalog().descriptors
        if item.exposure.mcp and item.execution_mode.value == "cloud_sync"
        and item.side_effect_level.value == "read" and item.confirmation_policy == "none")


def _descriptors_for_user(current_user: dict):
    tenant_id = str(current_user.get("team_id") or "default")
    grants = build_capability_authorization_grants(current_user, tenant_id, "web")
    permissions = set(build_profile(current_user).get("permissions", ()))
    selected = []
    for item in _mcp_descriptors():
        if item.data_classification not in grants.data_scopes and "*" not in grants.data_scopes:
            continue
        if item.authorization_policy.startswith("legacy:"):
            required = set(filter(None, item.authorization_policy.removeprefix("legacy:").split(",")))
            if required != {"authenticated"} and not required <= permissions:
                continue
        selected.append(item)
    return tuple(selected), grants


@router.post("/delegations")
def exchange_delegation(
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    service_credential: str | None = Header(default=None, alias="X-AI00-Service-Credential"),
):
    _require_service(service_credential)
    descriptors, actor_grants = _descriptors_for_user(current_user)
    if not descriptors:
        raise HTTPException(status_code=403, detail={"code": "no_mcp_capabilities_granted"})
    now = datetime.now(UTC)
    authentication_deadline = principal.authenticated_at + timedelta(hours=8)
    if authentication_deadline <= now:
        raise HTTPException(status_code=401, detail={"code": "authentication_freshness_required"})
    catalog = get_default_gateway().catalog()
    grant = DelegationGrant(
        delegation_id=f"dlg_{uuid.uuid4().hex}", delegated_by=str(current_user["gid"]),
        user_id=str(current_user["gid"]), tenant_id=str(current_user.get("team_id") or "default"),
        consumer_type=ConsumerType.MCP, consumer_id="ai00.mcp-gateway", consumer_version="2",
        catalog_release=catalog.release_id,
        capability_scopes=tuple(sorted({item.id for item in descriptors})),
        resource_scopes=tuple(sorted(actor_grants.resource_scopes)),
        data_scopes=tuple(sorted({item.data_classification for item in descriptors})),
        maximum_automation_level=AutomationLevel.A2,
        authentication_method=principal.authentication_method, authenticated_at=principal.authenticated_at,
        expires_at=min(now + timedelta(hours=1), authentication_deadline),
    )
    issued = issue_delegation(SqlDelegationStore(get_conn), grant)
    return {"delegation_id": grant.delegation_id, "delegation_token": issued.token,
            "catalog_release": grant.catalog_release, "expires_at": grant.expires_at.isoformat(),
            "capability_scopes": list(grant.capability_scopes),
            "descriptors": [item.model_dump(mode="json") for item in _mcp_descriptors()]}


def _identity(service_credential: str | None, delegation_token: str | None) -> ConsumerIdentity:
    _require_service(service_credential)
    if not delegation_token:
        raise HTTPException(status_code=401, detail={"code": "delegation_required"})
    try:
        grant = SqlDelegationStore(get_conn).consume_active(delegation_token)
    except DelegationError as exc:
        raise HTTPException(status_code=401, detail={"code": str(exc)}) from exc
    if grant.consumer_type is not ConsumerType.MCP or not grant.user_id:
        raise HTTPException(status_code=403, detail={"code": "mcp_delegation_required"})
    user = user_service.get_by_gid(grant.user_id)
    if not user or str(user.get("team_id") or "default") != grant.tenant_id:
        raise HTTPException(status_code=403, detail={"code": "delegated_membership_inactive"})
    return ConsumerIdentity(
        actor=ActorIdentity(user_id=grant.user_id, authentication_method=grant.authentication_method, authenticated_at=grant.authenticated_at),
        tenant=TenantIdentity(tenant_id=grant.tenant_id, membership="member",
            active_roles=tuple(filter(None, (user.get("org_role"), user.get("system_role"))))),
        consumer=ConsumerDescriptor(type=ConsumerType.MCP, consumer_id=grant.consumer_id, consumer_version=grant.consumer_version),
        delegation=DelegationContext(
            delegation_id=grant.delegation_id, delegated_by=grant.delegated_by,
            capability_scopes=grant.capability_scopes, resource_scopes=grant.resource_scopes,
            data_scopes=grant.data_scopes, catalog_release=grant.catalog_release,
            maximum_automation_level=grant.maximum_automation_level, expires_at=grant.expires_at),
    )


@router.post("/{capability_id}:invoke")
async def invoke(capability_id: str, body: McpInvokeRequest, request: Request,
    service_credential: str | None = Header(default=None, alias="X-AI00-Service-Credential"),
    delegation_token: str | None = Header(default=None, alias="X-AI00-Delegation")):
    identity = _identity(service_credential, delegation_token)
    request_id = request.headers.get("X-Request-ID") or f"mcp_{uuid.uuid4().hex}"
    if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$", request_id):
        raise HTTPException(status_code=400, detail={"code": "invalid_request_id"})
    result = await get_default_gateway().invoke(InvocationEnvelope(
        capability_id=capability_id, major_version=body.major_version,
        catalog_release=body.catalog_release, payload=body.payload, identity=identity,
        request_id=request_id, trace_id=request_id))
    return result.model_dump(mode="json")
