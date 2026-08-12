"""Temporary Gateway adapters for Project Management collaboration sessions."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, require_role
from plugins.project_management.project_management_backend.api.compatibility import (
    build_web_compatibility_envelope,
    invoke_compatibility,
)

router = APIRouter(prefix="/api/collab", tags=["collab"])
_MEMBER = require_role(
    "super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member"
)


class CreateSessionBody(BaseModel):
    section_gid: str


async def _invoke_project(request, current_user, principal, gateway, *, capability_id, operation, arguments):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(
        gateway,
        build_web_compatibility_envelope(
            gateway,
            capability_id=capability_id,
            payload={"operation": operation, "arguments": arguments},
            current_user=current_user,
            principal=principal,
            request_id=request_id,
            trace_id=request.headers.get("X-Trace-ID") or request_id,
            idempotency_key=request.headers.get("X-Idempotency-Key") if capability_id.endswith("change.apply") else None,
            approval_reference=request.headers.get("X-Capability-Approval") if capability_id.endswith("change.apply") else None,
        ),
    )
    if not result.ok:
        code = result.error.code if result.error else "provider_failed"
        status = 404 if code == "not_found" else 403 if code == "forbidden" else 422
        raise HTTPException(status, result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.get("/sessions")
async def list_sessions(request: Request, section_gid: Optional[str] = Query(None), current_user: dict = Depends(_MEMBER), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, capability_id="project.collaboration.read", operation="collaboration.sessions.list", arguments={"section_gid": section_gid})


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSessionBody, request: Request, current_user: dict = Depends(_MEMBER), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, capability_id="project.collaboration.change.apply", operation="collaboration.sessions.create", arguments={"section_gid": body.section_gid})


@router.get("/sessions/{gid}")
async def get_session(gid: str, request: Request, current_user: dict = Depends(_MEMBER), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, capability_id="project.collaboration.read", operation="collaboration.sessions.get", arguments={"gid": gid})


@router.post("/sessions/{gid}/join")
async def join_session(gid: str, request: Request, current_user: dict = Depends(_MEMBER), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, capability_id="project.collaboration.change.apply", operation="collaboration.sessions.join", arguments={"gid": gid})


@router.post("/sessions/{gid}/end")
async def end_session(gid: str, request: Request, current_user: dict = Depends(_MEMBER), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, capability_id="project.collaboration.change.apply", operation="collaboration.sessions.end", arguments={"gid": gid})
