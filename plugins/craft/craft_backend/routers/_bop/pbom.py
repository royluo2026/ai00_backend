"""REST compatibility adapter for governed PBOM change-point comparison."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.ids import next_gid

from ._constants import _READ

router = APIRouter(prefix="/api/bop", tags=["bop"])


async def _invoke_pbom_change_point(request, current_user, principal, gateway, version_gid):
    request_id = request.headers.get("X-Request-ID") or f"craft_pbom_change_point_legacy_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.pbom.change_point.get", payload={"operation": "get", "version_gid": version_gid},
        current_user=current_user, principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


@router.get("/versions/{gid}/pbom-change-point")
async def pbom_change_point(gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_pbom_change_point(request, _u, principal, gateway, gid)
