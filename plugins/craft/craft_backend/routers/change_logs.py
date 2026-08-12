"""Temporary legacy adapter for Project Management change-log reads."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from plugins.project_management.project_management_backend.api.compatibility import (
    build_web_compatibility_envelope,
    invoke_compatibility,
)

router = APIRouter(prefix="/api/change-logs", tags=["change_logs"])


@router.get("")
async def list_change_logs(
    request: Request,
    item_type: str | None = Query(None),
    item_gid: str | None = Query(None),
    list_gid: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    if not item_gid and not list_gid:
        raise HTTPException(400, "item_gid 或 list_gid 至少提供一个")
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    trace_id = request.headers.get("X-Trace-ID") or request_id
    result = await invoke_compatibility(
        gateway,
        build_web_compatibility_envelope(
            gateway,
            capability_id="project.change_log.read",
            payload={
                "operation": "change_logs.search",
                "arguments": {
                    "item_type": item_type,
                    "item_gid": item_gid,
                    "list_gid": list_gid,
                    "limit": limit,
                    "offset": offset,
                },
            },
            current_user=current_user,
            principal=principal,
            request_id=request_id,
            trace_id=trace_id,
        ),
    )
    if not result.ok:
        code = result.error.code if result.error else "provider_failed"
        status_code = 403 if code == "forbidden" else 400 if code == "invalid_input" else 422
        raise HTTPException(
            status_code=status_code,
            detail=result.error.model_dump(mode="json") if result.error else None,
        )
    return result.data["data"]
