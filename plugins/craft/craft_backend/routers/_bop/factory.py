"""Legacy BOP factory routes composed through the official Factory Provider."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from ..factory import _invoke
from ._constants import _ADMIN, _READ


router = APIRouter(prefix="/api/bop", tags=["bop"])


class CreateFactoryBody(BaseModel):
    name: str
    team_id: Optional[str] = None


class UpdateFactoryBody(BaseModel):
    name: Optional[str] = None
    team_id: Optional[str] = None


class CreateSectionBody(BaseModel):
    name: str
    sort_order: int = 0
    color: str = "#7287fd"
    canvas_x: float = 0
    canvas_y: float = 0
    canvas_w: float = 400
    canvas_h: float = 300


class UpdateSectionBody(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    color: Optional[str] = None
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
    canvas_w: Optional[float] = None
    canvas_h: Optional[float] = None
    owner_gid: Optional[str] = None


class CreateStationBody(BaseModel):
    code: str
    name: str = ""
    canvas_x: float = 0
    canvas_y: float = 0
    takt_time: float = 60
    height_mm: int = 1200


class UpdateStationBody(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
    takt_time: Optional[float] = None
    height_mm: Optional[int] = None


class CreateLayoutTemplateBody(BaseModel):
    name: str
    team_id: Optional[str] = None
    stations: list = Field(default_factory=list)


class ApplyLayoutTemplateBody(BaseModel):
    factory_section_gid: str
    drop_x: float = 0
    drop_y: float = 0


async def _get_structure(gid, request, user, principal, gateway):
    row = await _invoke(request, user, principal, gateway, "factory.structure.get", {"gid": gid})
    if not row: raise HTTPException(404, "记录不存在")
    return row


async def _update_structure(gid, body, request, user, principal, gateway):
    row = await _get_structure(gid, request, user, principal, gateway)
    values = body.model_dump(exclude_none=True) if hasattr(body, "model_dump") else dict(body)
    name = values.pop("name", None)
    updates = {"attributes": {**(row.get("attributes") or {}), **values}}
    if name is not None: updates["name"] = name
    return await _invoke(request, user, principal, gateway, "factory.structure.update", {"gid": gid, "expected_version": row["version"], "updates": updates}, write=True)


async def _archive_structure(gid, request, user, principal, gateway):
    row = await _get_structure(gid, request, user, principal, gateway)
    await _invoke(request, user, principal, gateway, "factory.structure.archive", {"gid": gid, "expected_version": row["version"]}, write=True)


@router.get("/factories")
async def list_factories(request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _invoke(request, _u, principal, gateway, "factory.structure.search", {"kind": "factory"})}


@router.post("/factories", status_code=201)
async def create_factory(body: CreateFactoryBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _invoke(request, _u, principal, gateway, "factory.structure.create", {"kind": "factory", "name": body.name, "attributes": {"team_id": body.team_id}}, write=True)}


@router.get("/factories/{gid}")
async def get_factory(gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _get_structure(gid, request, _u, principal, gateway)}


@router.patch("/factories/{gid}")
async def update_factory(gid: str, body: UpdateFactoryBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _update_structure(gid, body, request, _u, principal, gateway)}


@router.delete("/factories/{gid}", status_code=204)
async def delete_factory(gid: str, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _archive_structure(gid, request, _u, principal, gateway)


@router.get("/factories/{factory_gid}/sections")
async def list_sections(factory_gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _invoke(request, _u, principal, gateway, "factory.structure.search", {"kind": "section", "parent_gid": factory_gid})}


@router.post("/factories/{factory_gid}/sections", status_code=201)
async def create_section(factory_gid: str, body: CreateSectionBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    values = body.model_dump(); name = values.pop("name")
    return {"data": await _invoke(request, _u, principal, gateway, "factory.structure.create", {"kind": "section", "name": name, "parent_gid": factory_gid, "attributes": values}, write=True)}


@router.patch("/factory_sections/{gid}")
async def update_section(gid: str, body: UpdateSectionBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _update_structure(gid, body, request, _u, principal, gateway)}


@router.delete("/factory_sections/{gid}", status_code=204)
async def delete_section(gid: str, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _archive_structure(gid, request, _u, principal, gateway)


@router.get("/factory_sections/{section_gid}/stations")
async def list_stations(section_gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _invoke(request, _u, principal, gateway, "factory.structure.search", {"kind": "station", "parent_gid": section_gid})}


@router.post("/factory_sections/{section_gid}/stations", status_code=201)
async def create_station(section_gid: str, body: CreateStationBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    values = body.model_dump(); name = values.pop("name") or values["code"]
    return {"data": await _invoke(request, _u, principal, gateway, "factory.structure.create", {"kind": "station", "name": name, "parent_gid": section_gid, "attributes": values}, write=True)}


@router.patch("/factory_stations/{gid}")
async def update_station(gid: str, body: UpdateStationBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _update_structure(gid, body, request, _u, principal, gateway)}


@router.delete("/factory_stations/{gid}", status_code=204)
async def delete_station(gid: str, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _archive_structure(gid, request, _u, principal, gateway)


async def _layout_search(factory_gid, request, user, principal, gateway):
    rows = await _invoke(request, user, principal, gateway, "factory.resource_catalog.search", {"resource_type": "fixture"})
    result = []
    for row in rows:
        spec = row.get("specification") or {}
        if isinstance(spec, str):
            try: spec = json.loads(spec)
            except ValueError: spec = {}
        if spec.get("legacy_kind") == "layout_template" and spec.get("factory_gid") == factory_gid:
            result.append({**row, "stations": spec.get("stations", [])})
    return result


@router.get("/factories/{factory_gid}/layout_templates")
async def list_layout_templates(factory_gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _layout_search(factory_gid, request, _u, principal, gateway)}


@router.post("/factories/{factory_gid}/layout_templates", status_code=201)
async def create_layout_template(factory_gid: str, body: CreateLayoutTemplateBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"data": await _invoke(request, _u, principal, gateway, "factory.resource_catalog.create", {"resource_type": "fixture", "name": body.name, "specification": {"legacy_kind": "layout_template", "factory_gid": factory_gid, "team_id": body.team_id, "stations": body.stations}}, write=True)}


@router.get("/layout_templates/{gid}")
async def get_layout_template(gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    row = await _invoke(request, _u, principal, gateway, "factory.resource_catalog.get", {"gid": gid})
    if not row: raise HTTPException(404, "记录不存在")
    return {"data": row}


@router.patch("/layout_templates/{gid}")
async def update_layout_template(gid: str, body: dict, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    row = await _invoke(request, _u, principal, gateway, "factory.resource_catalog.get", {"gid": gid})
    if not row: raise HTTPException(404, "记录不存在")
    data = {"gid": gid, "expected_revision": row["revision"]}
    if "name" in body: data["name"] = body["name"]
    if "stations" in body:
        spec = row.get("specification") or {}
        if isinstance(spec, str): spec = json.loads(spec)
        data["specification"] = {**spec, "stations": body["stations"]}
    return {"data": await _invoke(request, _u, principal, gateway, "factory.resource_catalog.revise", data, write=True)}


@router.delete("/layout_templates/{gid}", status_code=204)
async def delete_layout_template(gid: str, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    row = await _invoke(request, _u, principal, gateway, "factory.resource_catalog.get", {"gid": gid})
    if not row: raise HTTPException(404, "记录不存在")
    if row.get("status") == "draft":
        await _invoke(request, _u, principal, gateway, "factory.resource_catalog.publish", {"gid": gid, "expected_revision": row["revision"]}, write=True)
        row = await _invoke(request, _u, principal, gateway, "factory.resource_catalog.get", {"gid": gid})
        revision = row["revision"]
    else: revision = row["revision"]
    await _invoke(request, _u, principal, gateway, "factory.resource_catalog.deprecate", {"gid": gid, "expected_revision": revision}, write=True)


@router.post("/layout_templates/{gid}/apply", status_code=201)
async def apply_layout_template(gid: str, body: ApplyLayoutTemplateBody, request: Request, _u=Depends(_ADMIN), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    row = await _invoke(request, _u, principal, gateway, "factory.resource_catalog.get", {"gid": gid})
    if not row: raise HTTPException(404, "记录不存在")
    spec = row.get("specification") or {}
    if isinstance(spec, str): spec = json.loads(spec)
    created = []
    for station in spec.get("stations", []):
        attrs = dict(station); attrs["canvas_x"] = body.drop_x + attrs.pop("rel_x", 0); attrs["canvas_y"] = body.drop_y + attrs.pop("rel_y", 0)
        created.append(await _invoke(request, _u, principal, gateway, "factory.structure.create", {"kind": "station", "name": attrs.get("name") or attrs.get("code") or "Station", "parent_gid": body.factory_section_gid, "attributes": attrs}, write=True))
    return {"data": created}
