"""User and device HTTP adapters for the Local Runtime control plane."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from plugins.device.device_backend.public import (
    activate_device, authenticate_device, complete_command, create_enrollment,
    heartbeat, lease_command, list_devices, revoke_device,
)
from backend.platform_sdk.auth import build_profile, get_current_user

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
    lease_id: str = Field(min_length=1)
    success: bool
    result: object | None = None
    error: str = Field(default="", max_length=4000)

def _device_auth(device_gid: str = Header(alias="X-AI00-Device-ID"), device_token: str = Header(alias="X-AI00-Device-Token")) -> dict:
    try:
        return authenticate_device(device_gid, device_token)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail="Invalid device credentials") from exc

@router.post("/devices/enrollments")
def enroll(body: EnrollmentBody, user: dict = Depends(get_current_user)):
    permissions = set(build_profile(user).get("permissions", []))
    if "system.tech_config" not in permissions:
        raise HTTPException(status_code=403, detail="Missing permission: system.tech_config")
    return {"success": True, "data": create_enrollment(user, body.display_name, body.team_gid, body.ttl_minutes)}

@router.get("/devices")
def devices(user: dict = Depends(get_current_user)):
    return {"success": True, "data": list_devices(user["gid"])}

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

@router.post("/device-runtime/commands/lease")
def runtime_lease(body: LeaseBody, device: dict = Depends(_device_auth)):
    return {"success": True, "data": lease_command(device["gid"], body.lease_seconds)}

@router.post("/device-runtime/commands/{command_gid}/complete")
def runtime_complete(command_gid: str, body: CompleteBody, device: dict = Depends(_device_auth)):
    try:
        complete_command(device["gid"], command_gid, body.lease_id, body.success, body.result, body.error)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True}
