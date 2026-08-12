"""Legacy annotation HTTP adapter; Project owns persistence."""
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


class AnnotationPutBody(BaseModel): data: Any = None


async def _invoke(request, user, principal, gateway, operation, arguments, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(gateway, capability_id="project.workbench.change.apply" if write else "project.workbench.read", payload={"operation": operation, "arguments": arguments}, current_user=user, principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id, idempotency_key=request.headers.get("X-Idempotency-Key") if write else None, approval_reference=request.headers.get("X-Capability-Approval") if write else None))
    if not result.ok: raise HTTPException(422, result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.get("/{key}")
async def get_annotation(key: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "annotations.get", {"key": key})


@router.put("/{key}")
async def put_annotation(key: str, body: AnnotationPutBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "annotations.put", {"key": key, "data": body.data}, True)
