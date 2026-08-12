"""
backend/routers/item_entries.py
───────────────────────────────
条目沟通历史云端持久化（item_entries）

GET  /api/item-entries/{item_type}/{item_gid}   → { entries: [...] }
PUT  /api/item-entries/{item_type}/{item_gid}   → { success, count, entries }
DELETE /api/item-entries/{item_type}/{item_gid} → { success }
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from plugins.project_management.project_management_backend.api.compatibility import (
    build_web_compatibility_envelope,
    invoke_compatibility,
)

router = APIRouter(prefix="/api/item-entries", tags=["item_entries"])


class EntryPutBody(BaseModel):
    entries: list = []


async def _invoke_project(
    request: Request,
    current_user: dict,
    principal,
    gateway,
    *,
    capability_id: str,
    operation: str,
    arguments: dict,
):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    trace_id = request.headers.get("X-Trace-ID") or request_id
    result = await invoke_compatibility(
        gateway,
        build_web_compatibility_envelope(
            gateway,
            capability_id=capability_id,
            payload={"operation": operation, "arguments": arguments},
            current_user=current_user,
            principal=principal,
            request_id=request_id,
            trace_id=trace_id,
            idempotency_key=request.headers.get("X-Idempotency-Key"),
            approval_reference=request.headers.get("X-Capability-Approval"),
        ),
    )
    if not result.ok:
        raise HTTPException(
            status_code=422,
            detail=result.error.model_dump(mode="json") if result.error else None,
        )
    return result.data["data"]


@router.get("/{item_type}/{item_gid}")
async def get_item_entries(
    item_type: str,
    item_gid: str,
    request: Request,
    current_user=Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_project(
        request, current_user, principal, gateway,
        capability_id="project.list.read",
        operation="item_entries.get",
        arguments={"item_type": item_type, "item_gid": item_gid},
    )


@router.put("/{item_type}/{item_gid}")
async def put_item_entries(
    item_type: str,
    item_gid: str,
    body: EntryPutBody,
    request: Request,
    current_user=Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_project(
        request, current_user, principal, gateway,
        capability_id="project.list.change.apply",
        operation="item_entries.replace",
        arguments={
            "item_type": item_type,
            "item_gid": item_gid,
            "entries": body.entries or [],
        },
    )


@router.delete("/{item_type}/{item_gid}")
async def delete_item_entries(
    item_type: str,
    item_gid: str,
    request: Request,
    current_user=Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_project(
        request, current_user, principal, gateway,
        capability_id="project.list.change.apply",
        operation="item_entries.delete",
        arguments={"item_type": item_type, "item_gid": item_gid},
    )
