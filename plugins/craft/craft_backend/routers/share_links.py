"""Temporary Gateway adapters for Project Management share links."""
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from plugins.project_management.project_management_backend.api.compatibility import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(tags=["share_links"])

class ShareLinkBody(BaseModel):
    target_type: str
    target_gid: str
    item_type: Optional[str] = None
    display_name: str = ""
    expires_at: Optional[str] = None

async def _invoke(request, user, principal, gateway, capability_id, operation, arguments):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    write = capability_id.endswith("change.apply")
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload={"operation": operation, "arguments": arguments},
        current_user=user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_failed"
        raise HTTPException(404 if code == "not_found" else 403 if code == "forbidden" else 422,
                            result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]

@router.post("/api/share-links", status_code=status.HTTP_201_CREATED)
async def create_share_link(body: ShareLinkBody, request: Request, user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, user, principal, gateway, "project.sharing.change.apply", "share_links.create", body.model_dump())

@router.get("/api/share-links/{token}")
async def resolve_share_link(token: str, request: Request, user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, user, principal, gateway, "project.sharing.read", "share_links.resolve", {"token": token})

@router.delete("/api/share-links/{token}")
async def delete_share_link(token: str, request: Request, user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, user, principal, gateway, "project.sharing.change.apply", "share_links.delete", {"token": token})
