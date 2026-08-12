"""Legacy `/api/factory` routes backed exclusively by Factory Capabilities."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, require_role
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility


router = APIRouter(prefix="/api/factory", tags=["factory"])
_READ = require_role("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "project_admin")


class RegisterAssetBody(BaseModel):
    asset_no: str
    template_gid: Optional[str] = None
    meta: dict = Field(default_factory=dict)


class UpdateAssetBody(BaseModel):
    asset_no: Optional[str] = None
    template_gid: Optional[str] = None
    meta: Optional[dict] = None


class SectionBody(BaseModel):
    name: str
    factory_gid: str
    sort_order: int = 0
    color: str = "#7287fd"


class UpdateSectionBody(BaseModel):
    name: Optional[str] = None
    factory_gid: Optional[str] = None
    sort_order: Optional[int] = None
    color: Optional[str] = None


class StationBody(BaseModel):
    code: str = ""
    name: str = ""
    factory_section_gid: str
    takt_time: float = 60
    height_mm: int = 1200
    meta: dict = Field(default_factory=dict)


class UpdateStationBody(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    factory_section_gid: Optional[str] = None
    takt_time: Optional[float] = None
    height_mm: Optional[int] = None
    meta: Optional[dict] = None


async def _invoke(request, user, principal, gateway, capability_id, payload, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"factory_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload=payload, current_user=user, principal=principal,
        request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=(request.headers.get("X-Idempotency-Key") or request_id) if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400, "version_conflict": 409}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


async def _asset_current(gid, request, user, principal, gateway):
    row = await _invoke(request, user, principal, gateway, "factory.asset.get", {"gid": gid})
    if not row: raise HTTPException(404, "资产不存在")
    return row


def _asset_routes(kind: str, path: str):
    async def list_assets(request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
        data = await _invoke(request, current_user, principal, gateway, "factory.asset.search", {"asset_type": kind})
        return {"success": True, "data": data}

    async def register(body: RegisterAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
        data = await _invoke(request, current_user, principal, gateway, "factory.asset.register", {"asset_no": body.asset_no, "asset_type": kind, "catalog_gid": body.template_gid, "meta": body.meta}, write=True)
        return {"success": True, "data": {**data, "asset_no": body.asset_no}}

    async def remove(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
        row = await _asset_current(gid, request, current_user, principal, gateway)
        await _invoke(request, current_user, principal, gateway, "factory.asset.scrap", {"gid": gid, "expected_version": row["version"]}, write=True)
        return {"success": True}

    async def maintenance(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
        row = await _asset_current(gid, request, current_user, principal, gateway)
        await _invoke(request, current_user, principal, gateway, "factory.asset.maintenance.start", {"gid": gid, "expected_version": row["version"]}, write=True)
        return {"success": True}

    async def complete(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
        row = await _asset_current(gid, request, current_user, principal, gateway)
        await _invoke(request, current_user, principal, gateway, "factory.asset.maintenance.complete", {"gid": gid, "expected_version": row["version"]}, write=True)
        return {"success": True}

    async def scrap(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
        row = await _asset_current(gid, request, current_user, principal, gateway)
        await _invoke(request, current_user, principal, gateway, "factory.asset.scrap", {"gid": gid, "expected_version": row["version"]}, write=True)
        return {"success": True}

    async def patch(gid: str, body: UpdateAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
        row = await _asset_current(gid, request, current_user, principal, gateway)
        updates = body.model_dump(exclude_none=True)
        if "template_gid" in updates: updates["catalog_gid"] = updates.pop("template_gid")
        await _invoke(request, current_user, principal, gateway, "factory.asset.update", {"gid": gid, "expected_version": row["version"], "updates": updates}, write=True)
        return {"success": True}

    return list_assets, register, remove, maintenance, complete, scrap, patch


(_list_tools, _register_tool, _delete_tool, _tool_maintenance, _tool_return, _tool_scrap, _patch_tool) = _asset_routes("tool", "tools")
(_list_equipments, _register_equipment, _delete_equipment, _equipment_maintenance, _equipment_return, _equipment_scrap, _patch_equipment) = _asset_routes("equipment", "equipments")
(_list_fixtures, _register_fixture, _delete_fixture, _fixture_maintenance, _fixture_return, _fixture_scrap, _patch_fixture) = _asset_routes("fixture", "fixtures")


@router.get("/tools")
async def list_tools(request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _list_tools(request, current_user, principal, gateway)

@router.post("/tools", status_code=201)
async def register_tool(body: RegisterAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _register_tool(body, request, current_user, principal, gateway)

@router.delete("/tools/{gid}")
async def delete_tool(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _delete_tool(gid, request, current_user, principal, gateway)

@router.post("/tools/{gid}/maintenance")
async def tool_to_maintenance(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _tool_maintenance(gid, request, current_user, principal, gateway)

@router.post("/tools/{gid}/return")
async def tool_return(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _tool_return(gid, request, current_user, principal, gateway)

@router.post("/tools/{gid}/scrap")
async def tool_scrap(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _tool_scrap(gid, request, current_user, principal, gateway)

@router.patch("/tools/{gid}")
async def patch_tool(gid: str, body: UpdateAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _patch_tool(gid, body, request, current_user, principal, gateway)


@router.get("/equipments")
async def list_equipments(request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _list_equipments(request, current_user, principal, gateway)

@router.post("/equipments", status_code=201)
async def register_equipment(body: RegisterAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _register_equipment(body, request, current_user, principal, gateway)

@router.delete("/equipments/{gid}")
async def delete_equipment(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _delete_equipment(gid, request, current_user, principal, gateway)

@router.post("/equipments/{gid}/maintenance")
async def equipment_to_maintenance(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _equipment_maintenance(gid, request, current_user, principal, gateway)

@router.post("/equipments/{gid}/return")
async def equipment_return(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _equipment_return(gid, request, current_user, principal, gateway)

@router.post("/equipments/{gid}/scrap")
async def equipment_scrap(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _equipment_scrap(gid, request, current_user, principal, gateway)

@router.patch("/equipments/{gid}")
async def patch_equipment(gid: str, body: UpdateAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _patch_equipment(gid, body, request, current_user, principal, gateway)


@router.get("/fixtures")
async def list_fixtures(request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _list_fixtures(request, current_user, principal, gateway)

@router.post("/fixtures", status_code=201)
async def register_fixture(body: RegisterAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _register_fixture(body, request, current_user, principal, gateway)

@router.delete("/fixtures/{gid}")
async def delete_fixture(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _delete_fixture(gid, request, current_user, principal, gateway)

@router.post("/fixtures/{gid}/maintenance")
async def fixture_to_maintenance(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _fixture_maintenance(gid, request, current_user, principal, gateway)

@router.post("/fixtures/{gid}/return")
async def fixture_return(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _fixture_return(gid, request, current_user, principal, gateway)

@router.post("/fixtures/{gid}/scrap")
async def fixture_scrap(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _fixture_scrap(gid, request, current_user, principal, gateway)

@router.patch("/fixtures/{gid}")
async def patch_fixture(gid: str, body: UpdateAssetBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _patch_fixture(gid, body, request, current_user, principal, gateway)


@router.get("/sections")
async def list_sections(request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"success": True, "data": await _invoke(request, current_user, principal, gateway, "factory.structure.search", {"kind": "section"})}


@router.post("/sections", status_code=201)
async def create_section(body: SectionBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "factory.structure.create", {"kind": "section", "name": body.name, "parent_gid": body.factory_gid, "attributes": {"sort_order": body.sort_order, "color": body.color}}, write=True)
    return {"success": True, "data": data}


@router.get("/stations")
async def list_stations(request: Request, current_user=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"success": True, "data": await _invoke(request, current_user, principal, gateway, "factory.structure.search", {"kind": "station"})}


@router.post("/stations", status_code=201)
async def create_station(body: StationBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "factory.structure.create", {"kind": "station", "name": body.name or body.code, "parent_gid": body.factory_section_gid, "attributes": {"code": body.code, "takt_time": body.takt_time, "height_mm": body.height_mm, **body.meta}}, write=True)
    return {"success": True, "data": data}


async def _patch_structure(gid, body, request, user, principal, gateway):
    row = await _invoke(request, user, principal, gateway, "factory.structure.get", {"gid": gid})
    if not row: raise HTTPException(404, "记录不存在")
    values = body.model_dump(exclude_none=True)
    name = values.pop("name", None); parent = values.pop("factory_gid", values.pop("factory_section_gid", None))
    updates = {"attributes": {**(row.get("attributes") or {}), **values}}
    if name is not None: updates["name"] = name
    if parent is not None: updates["parent_gid"] = parent
    await _invoke(request, user, principal, gateway, "factory.structure.update", {"gid": gid, "expected_version": row["version"], "updates": updates}, write=True)
    return {"success": True}


@router.patch("/sections/{gid}")
async def patch_section(gid: str, body: UpdateSectionBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _patch_structure(gid, body, request, current_user, principal, gateway)


@router.patch("/stations/{gid}")
async def patch_station(gid: str, body: UpdateStationBody, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _patch_structure(gid, body, request, current_user, principal, gateway)


async def _archive(gid, request, user, principal, gateway):
    row = await _invoke(request, user, principal, gateway, "factory.structure.get", {"gid": gid})
    if not row: raise HTTPException(404, "记录不存在")
    await _invoke(request, user, principal, gateway, "factory.structure.archive", {"gid": gid, "expected_version": row["version"]}, write=True)
    return {"success": True}


@router.delete("/sections/{gid}")
async def delete_section(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _archive(gid, request, current_user, principal, gateway)


@router.delete("/stations/{gid}")
async def delete_station(gid: str, request: Request, current_user=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _archive(gid, request, current_user, principal, gateway)
