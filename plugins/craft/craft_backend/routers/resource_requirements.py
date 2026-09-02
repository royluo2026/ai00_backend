"""Thin Web compatibility adapters for governed Craft resource standards."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, require_role
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/craft", tags=["craft_resource_requirements"])

_READ = require_role("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "knowledge_admin")
_REVIEW = require_role("super_admin", "knowledge_admin", "project_admin")


async def _invoke_resource(request, current_user, principal, gateway, capability_id: str, payload: dict[str, Any]):
    request_id = request.headers.get("X-Request-ID") or f"craft_resource_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway,
        capability_id=capability_id,
        payload=payload,
        current_user=current_user,
        principal=principal,
        request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=(request.headers.get("X-Idempotency-Key") or request_id) if not capability_id.endswith(".search") else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_failed"
        status = {
            "invalid_input": 400,
            "permission_denied": 403,
            "resource_not_found": 404,
            "resource_alias_not_found": 404,
            "resource_staging_not_found": 404,
            "resource_code_conflict": 409,
            "resource_alias_conflict": 409,
            "resource_version_conflict": 409,
            "resource_in_use": 409,
            "resource_staging_conflict": 409,
            "resource_type_mismatch": 422,
        }.get(code, 422)
        raise HTTPException(status_code=status, detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResourceCreateBody(_ClosedModel):
    resource_type: Literal["socket", "tool", "fixture", "equipment"]
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="manual", min_length=1, max_length=255)


class ResourceUpdateBody(_ClosedModel):
    expected_resource_version: int = Field(ge=1)
    code: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    attributes: dict[str, Any] | None = None


class ResourceRetireBody(_ClosedModel):
    expected_resource_version: int = Field(ge=1)


class AliasCreateBody(_ClosedModel):
    alias_value: str = Field(min_length=1, max_length=255)


class StagingDecisionBody(_ClosedModel):
    expected_staging_version: int = Field(ge=1)
    review_note: str | None = Field(default=None, max_length=1000)


class StagingResolveBody(StagingDecisionBody):
    resource_gid: str = Field(min_length=1, max_length=128)


@router.get("/resource-requirements")
async def list_resource_requirements(
    request: Request,
    resource_type: Literal["socket", "tool", "fixture", "equipment"] | None = Query(None),
    status: Literal["active", "retired", "all"] = Query("active"),
    q: str | None = Query(None, max_length=200),
    cursor: str | None = Query(None),
    page_size: int = Query(100, ge=1, le=200),
    current_user: dict = Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    payload = {"status": status, "page_size": page_size}
    if resource_type: payload["resource_type"] = resource_type
    if q: payload["q"] = q
    if cursor: payload["cursor"] = cursor
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.search", payload)
    return {"success": True, "data": data.get("items", []), "next_cursor": data.get("next_cursor")}


@router.post("/resource-requirements", status_code=201)
async def create_resource_requirement(body: ResourceCreateBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.create", body.model_dump())
    return {"success": True, "data": data}


@router.patch("/resource-requirements/{gid}")
async def update_resource_requirement(gid: str, body: ResourceUpdateBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.update", {"gid": gid, **body.model_dump(exclude_none=True)})
    return {"success": True, "data": data}


@router.post("/resource-requirements/{gid}/retire")
async def retire_resource_requirement(gid: str, body: ResourceRetireBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.retire", {"gid": gid, **body.model_dump(exclude_none=True)})
    return {"success": True, "data": data}


@router.post("/resource-requirements/{resource_gid}/aliases", status_code=201)
async def create_resource_alias(resource_gid: str, body: AliasCreateBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.alias.create", {"resource_gid": resource_gid, **body.model_dump()})
    return {"success": True, "data": data}


@router.delete("/resource-requirements/{resource_gid}/aliases/{alias_gid}")
async def delete_resource_alias(resource_gid: str, alias_gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.alias.delete", {"resource_gid": resource_gid, "alias_gid": alias_gid})
    return {"success": True, "data": data}


@router.get("/tc-resource-staging")
async def list_resource_staging(request: Request, version_gid: str = Query(..., min_length=1), match_status: str | None = Query(None, max_length=16), cursor: str | None = Query(None), page_size: int = Query(100, ge=1, le=200), current_user: dict = Depends(_REVIEW), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    payload: dict[str, Any] = {"page_size": page_size, "version_gid": version_gid}
    if match_status: payload["match_status"] = match_status
    if cursor: payload["cursor"] = cursor
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.staging.search", payload)
    return {"success": True, "data": data.get("items", []), "next_cursor": data.get("next_cursor")}


@router.post("/tc-resource-staging/{staging_gid}/resolve")
async def resolve_resource_staging(staging_gid: str, body: StagingResolveBody, request: Request, current_user: dict = Depends(_REVIEW), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.staging.resolve", {"staging_gid": staging_gid, **body.model_dump(exclude_none=True)})
    return {"success": True, "data": data}


@router.post("/tc-resource-staging/{staging_gid}/ignore")
async def ignore_resource_staging(staging_gid: str, body: StagingDecisionBody, request: Request, current_user: dict = Depends(_REVIEW), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke_resource(request, current_user, principal, gateway, "craft.resource_requirement.staging.ignore", {"staging_gid": staging_gid, **body.model_dump(exclude_none=True)})
    return {"success": True, "data": data}
