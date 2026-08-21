"""
backend/routers/craft_library.py
──────────────────────────────────
工艺元素库 API（tool/equipment/fixture_templates + standard_fasteners + standard_part_names）

端点前缀：/api/craft_lib
  GET/POST /tools
  GET/PATCH/DELETE /tools/{gid}
  POST /tools/{gid}/obsolete

  (同样适用于 /equipments, /fixtures)

  GET/POST /fasteners
  GET/PATCH/DELETE /fasteners/{gid}

  GET/POST /part_names
  GET/DELETE /part_names/{gid}
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user, require_role
from backend.platform_sdk.ids import next_gid
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(prefix="/api/craft_lib", tags=["craft_library"])
_log = __import__('logging').getLogger(__name__)

_READ = require_role("super_admin", "team_admin", "project_admin",
                     "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "knowledge_admin")


async def _invoke_library(request, current_user, principal, gateway, operation, *, q=None):
    request_id = request.headers.get("X-Request-ID") or f"craft_library_legacy_{next_gid()}"
    arguments = {"operation": operation}
    if q:
        arguments["q"] = q
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.library.read", payload=arguments,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"].get("items", [])


async def _invoke_change(request, current_user, principal, gateway, operation, *, gid=None, record=None, items=None, meta=None, alias=None):
    request_id = request.headers.get("X-Request-ID") or f"craft_library_legacy_{next_gid()}"
    arguments = {"operation": operation}
    if gid is not None:
        arguments["gid"] = gid
    if record is not None:
        arguments["record"] = record
    if items is not None:
        arguments["items"] = items
    if meta is not None:
        arguments["meta"] = meta
    if alias is not None:
        arguments["alias"] = alias
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.library.change.apply", payload=arguments,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


class TemplateBody(BaseModel):
    name: str
    category: str = ""
    spec: dict = {}


class ToolBody(BaseModel):
    vpps: Optional[str] = None
    name: str = ""
    gun_model: str = ""
    matou_part_no: str = ""
    importance: str = ""
    gun_type: str = ""
    wireless: str = ""
    output_square: str = ""
    torque_min: str = ""
    torque_recommended: str = ""
    cad_model_no: str = ""
    socket_model: str = ""
    fastener_type: str = ""
    fastener_params: str = ""
    extension_model: str = ""
    socket_cad_no: str = ""
    extension_cad_no: str = ""


class UpdateTemplateBody(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    spec: Optional[dict] = None


class FastenerBody(BaseModel):
    fastener_type: str = ""
    part_no: str = ""
    name: str = ""
    thread_spec: str = ""
    model: str = ""
    shank_length: str = ""
    guide_type: str = ""
    guide_length: str = ""
    has_adhesive: str = ""
    drive_size: str = ""
    flange_diameter: str = ""
    first_vehicle: str = ""


class UpdateFastenerBody(BaseModel):
    fastener_type: Optional[str] = None
    part_no: Optional[str] = None
    name: Optional[str] = None
    thread_spec: Optional[str] = None
    model: Optional[str] = None
    shank_length: Optional[str] = None
    guide_type: Optional[str] = None
    guide_length: Optional[str] = None
    has_adhesive: Optional[str] = None
    drive_size: Optional[str] = None
    flange_diameter: Optional[str] = None
    first_vehicle: Optional[str] = None


_FLEX_TYPE_VALUES = {'刚性件', '半柔性', '柔性', '待定'}

class PartNameBody(BaseModel):
    vpps_description: str = ""
    part_category: str = ""
    description: str = ""
    level: str = ""
    vpps_desc_cn: str = ""
    vpps: Optional[str] = None
    importance: str = ""
    vehicle_model: str = ""
    parent_vpps: str = ""
    status: str = "active"
    meta: dict = {}
    flex_type: str = "待定"
    ref_main_vpps: str = ""
    ref_main_vpps_desc: str = ""
    ref_install_direction: str = ""
    ref_static_clearance: str = ""
    ref_install_clearance: str = ""
    alias: list = []


def _list_template(table: str, current_user: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT gid, name, category, status, spec, created_at FROM {table} ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "name": r["name"], "category": r["category"], "status": r["status"],
         "spec": r["spec"], "created_at": str(r["created_at"])}
        for r in rows
    ]}


def _create_template(table: str, body: TemplateBody, current_user: dict):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {table} (gid, name, category, spec, team_id) VALUES (%s, %s, %s, %s, %s)",
                (gid, body.name, body.category,
                 json.dumps(body.spec, ensure_ascii=False),
                 current_user.get("team_id"))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "name": body.name}}


def _obsolete_template(table: str, gid: str, current_user: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET status = 'obsolete' WHERE gid = %s AND status = 'active'",
                (gid,)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="记录不存在或已不可废弃")
        conn.commit()
    return {"success": True}


def _patch_record(table: str, gid: str, body, allowed_fields: list):
    """通用 PATCH：只更新客户端发送的字段"""
    fields = body.dict(exclude_unset=True)
    fields = {k: v for k, v in fields.items() if k in allowed_fields}
    if not fields:
        return {"success": True}
    set_parts = []
    values = []
    for k, v in fields.items():
        if k == "spec" and isinstance(v, dict):
            set_parts.append(f"{k} = %s")
            values.append(json.dumps(v, ensure_ascii=False))
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)
    values.append(gid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET {', '.join(set_parts)} WHERE gid = %s", values
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="记录不存在")
        conn.commit()
    return {"success": True}


# ── 工具模板 ──────────────────────────────────────────────────────

_TOOL_COLS = ("gid, vpps, name, gun_model, matou_part_no, importance, gun_type, "
              "wireless, output_square, torque_min, torque_recommended, cad_model_no, "
              "socket_model, fastener_type, fastener_params, extension_model, "
              "socket_cad_no, extension_cad_no, status, created_at")


@router.get("/tools")
async def list_tools(request: Request, current_user: dict = Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"success": True, "data": await _invoke_library(request, current_user, principal, gateway, "tools.list")}


@router.post("/tools", status_code=201)
async def create_tool(body: ToolBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "tools.create", record=body.dict(exclude_unset=True))
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_tpl_vpps_tools "
                "(gid, vpps, name, gun_model, matou_part_no, importance, gun_type, "
                "wireless, output_square, torque_min, torque_recommended, cad_model_no, "
                "socket_model, fastener_type, fastener_params, extension_model, "
                "socket_cad_no, extension_cad_no, team_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.vpps, body.name, body.gun_model, body.matou_part_no,
                 body.importance, body.gun_type, body.wireless, body.output_square,
                 body.torque_min, body.torque_recommended, body.cad_model_no,
                 body.socket_model, body.fastener_type, body.fastener_params,
                 body.extension_model, body.socket_cad_no, body.extension_cad_no,
                 current_user.get("team_id"))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "vpps": body.vpps}}


@router.delete("/tools/{gid}")
async def delete_tool(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "tools.delete", gid=gid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_tpl_vpps_tools WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="工具模板不存在")
        conn.commit()
    return {"success": True}


@router.patch("/tools/{gid}")
async def update_tool(gid: str, body: ToolBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "tools.update", gid=gid, record=body.dict(exclude_unset=True))
    allowed = ["vpps","name","gun_model","matou_part_no","importance","gun_type",
               "wireless","output_square","torque_min","torque_recommended","cad_model_no",
               "socket_model","fastener_type","fastener_params","extension_model",
               "socket_cad_no","extension_cad_no"]
    return _patch_record("workmanship_tpl_vpps_tools", gid, body, allowed)


@router.post("/tools/{gid}/obsolete")
async def obsolete_tool(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "tools.obsolete", gid=gid)
    return _obsolete_template("workmanship_tpl_vpps_tools", gid, current_user)


# ── 设备模板 ──────────────────────────────────────────────────────

@router.get("/equipments")
async def list_equipments(request: Request, current_user: dict = Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"success": True, "data": await _invoke_library(request, current_user, principal, gateway, "equipments.list")}


@router.post("/equipments", status_code=201)
async def create_equipment(body: TemplateBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "equipments.create", record=body.dict(exclude_unset=True))
    return _create_template("workmanship_tpl_vpps_equipments", body, current_user)


@router.post("/equipments/{gid}/obsolete")
async def obsolete_equipment(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "equipments.obsolete", gid=gid)
    return _obsolete_template("workmanship_tpl_vpps_equipments", gid, current_user)


@router.patch("/equipments/{gid}")
async def update_equipment(gid: str, body: UpdateTemplateBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "equipments.update", gid=gid, record=body.dict(exclude_unset=True))
    return _patch_record("workmanship_tpl_vpps_equipments", gid, body, ["name", "category", "spec"])


# ── 工装模板 ──────────────────────────────────────────────────────

@router.get("/fixtures")
async def list_fixtures(request: Request, current_user: dict = Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"success": True, "data": await _invoke_library(request, current_user, principal, gateway, "fixtures.list")}


@router.post("/fixtures", status_code=201)
async def create_fixture(body: TemplateBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "fixtures.create", record=body.dict(exclude_unset=True))
    return _create_template("workmanship_tpl_vpps_fixtures", body, current_user)


@router.post("/fixtures/{gid}/obsolete")
async def obsolete_fixture(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "fixtures.obsolete", gid=gid)
    return _obsolete_template("workmanship_tpl_vpps_fixtures", gid, current_user)


@router.patch("/fixtures/{gid}")
async def update_fixture(gid: str, body: UpdateTemplateBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "fixtures.update", gid=gid, record=body.dict(exclude_unset=True))
    return _patch_record("workmanship_tpl_vpps_fixtures", gid, body, ["name", "category", "spec"])


# ── 标准紧固件 ────────────────────────────────────────────────────

_FASTENER_COLS = ("gid, fastener_type, part_no, name, thread_spec, model, "
                  "shank_length, guide_type, guide_length, has_adhesive, "
                  "drive_size, flange_diameter, first_vehicle, status, created_at")


@router.get("/fasteners")
async def list_fasteners(request: Request, current_user: dict = Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return {"success": True, "data": await _invoke_library(request, current_user, principal, gateway, "fasteners.list")}


@router.post("/fasteners", status_code=201)
async def create_fastener(body: FastenerBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "fasteners.create", record=body.dict(exclude_unset=True))
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_tpl_fastener_spec "
                "(gid, fastener_type, part_no, name, thread_spec, model, "
                "shank_length, guide_type, guide_length, has_adhesive, "
                "drive_size, flange_diameter, first_vehicle, team_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.fastener_type, body.part_no, body.name,
                 body.thread_spec, body.model, body.shank_length,
                 body.guide_type, body.guide_length, body.has_adhesive,
                 body.drive_size, body.flange_diameter, body.first_vehicle,
                 current_user.get("team_id"))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.delete("/fasteners/{gid}")
async def delete_fastener(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "fasteners.delete", gid=gid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_tpl_fastener_spec WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="紧固件不存在")
        conn.commit()
    return {"success": True}


@router.patch("/fasteners/{gid}")
async def update_fastener(gid: str, body: UpdateFastenerBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "fasteners.update", gid=gid, record=body.dict(exclude_unset=True))
    return _patch_record("workmanship_tpl_fastener_spec", gid, body,
                         ["fastener_type", "part_no", "name", "thread_spec", "model",
                          "shank_length", "guide_type", "guide_length", "has_adhesive",
                          "drive_size", "flange_diameter", "first_vehicle"])


# ── 标准零件名 ────────────────────────────────────────────────────

@router.get("/part_names")
async def list_part_names(
    q: Optional[str] = Query(None),
    request: Request = None,
    current_user: dict = Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return {"success": True, "data": await _invoke_library(request, current_user, principal, gateway, "part_names.list", q=q)}


@router.post("/part_names", status_code=201)
async def create_part_name(body: PartNameBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "part_names.create", record=body.dict(exclude_unset=True))
    if body.flex_type not in _FLEX_TYPE_VALUES:
        raise HTTPException(status_code=422, detail=f"flex_type 必须是 {sorted(_FLEX_TYPE_VALUES)} 之一")
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_tpl_vpps_parts "
                "(gid, vpps_description, part_category, description, level, vpps_desc_cn, vpps, "
                "importance, vehicle_model, parent_vpps, status, meta, team_id, "
                "flex_type, ref_main_vpps, ref_main_vpps_desc, "
                "ref_install_direction, ref_static_clearance, ref_install_clearance, alias) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, body.vpps_description, body.part_category, body.description,
                 body.level, body.vpps_desc_cn, body.vpps,
                 body.importance, body.vehicle_model, body.parent_vpps, body.status,
                 json.dumps(body.meta, ensure_ascii=False),
                 current_user.get("team_id"),
                 body.flex_type, body.ref_main_vpps, body.ref_main_vpps_desc,
                 body.ref_install_direction, body.ref_static_clearance, body.ref_install_clearance,
                 json.dumps([]))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.delete("/part_names/{gid}")
async def delete_part_name(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "part_names.delete", gid=gid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_tpl_vpps_parts WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="零件名不存在")
        conn.commit()
    return {"success": True}


@router.patch("/part_names/{gid}")
async def update_part_name(gid: str, body: PartNameBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "part_names.update", gid=gid, record=body.dict(exclude_unset=True))
    if body.dict(exclude_unset=True).get("flex_type") not in (None, *_FLEX_TYPE_VALUES):
        raise HTTPException(status_code=422, detail=f"flex_type 必须是 {sorted(_FLEX_TYPE_VALUES)} 之一")
    allowed = [
        "vpps_description", "part_category", "description", "level", "vpps_desc_cn",
        "vpps", "importance", "vehicle_model", "parent_vpps", "status",
        "flex_type", "ref_main_vpps", "ref_main_vpps_desc",
        "ref_install_direction", "ref_static_clearance", "ref_install_clearance", "alias",
    ]
    return _patch_record("workmanship_tpl_vpps_parts", gid, body, allowed)


class AcceptAliasBody(BaseModel):
    alias: str          # PBOM 中的描述字符串，将成为别名
    pbom_part_gid: str  # 触发此次判定的 PBOM 零件 gid（可为空串）


# ── 批量操作（来自 PBOM 核对页面）───────────────────────────────


class BatchAddFromPbomEntry(BaseModel):
    vpps: str
    vpps_desc_cn: str = ""
    vpps_description: str = ""


class BatchAddFromPbomBody(BaseModel):
    entries: list[BatchAddFromPbomEntry]
    meta: dict = {}   # {added_by, project, added_at}


@router.post("/part_names/batch_add_from_pbom")
async def batch_add_part_names_from_pbom(body: BatchAddFromPbomBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "part_names.batch_add_from_pbom", items=[item.dict() for item in body.entries], meta=body.meta)
    """将 PBOM 中"无主数据"零件批量写入 vpps_parts（已存在则跳过）。"""
    added = 0
    skipped = 0
    team_id = current_user.get("team_id") or None  # 空字符串转 None，避免 FK 违反
    with get_conn() as conn:
        with conn.cursor() as cur:
            for entry in body.entries:
                vpps = (entry.vpps or "").strip()
                if not vpps:
                    skipped += 1
                    continue
                cur.execute("SELECT gid FROM workmanship_tpl_vpps_parts WHERE vpps = %s", (vpps,))
                if cur.fetchone():
                    skipped += 1
                    continue
                gid = str(next_gid())
                cur.execute(
                    "INSERT INTO workmanship_tpl_vpps_parts "
                    "(gid, vpps_description, vpps_desc_cn, vpps, status, meta, team_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (gid, entry.vpps_description or entry.vpps_desc_cn or "",
                     entry.vpps_desc_cn or "", vpps, "有效",
                     json.dumps(body.meta, ensure_ascii=False),
                     team_id),
                )
                added += 1
        conn.commit()
    return {"success": True, "added": added, "skipped": skipped}


class BatchAliasItem(BaseModel):
    vpps_part_gid: str
    alias: str
    pbom_part_gid: str = ""


class BatchAcceptAliasBody(BaseModel):
    items: list[BatchAliasItem]
    meta: dict = {}   # {added_by, project, added_at}


@router.post("/part_names/batch_accept_alias")
async def batch_accept_vpps_alias(body: BatchAcceptAliasBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "part_names.batch_accept_alias", items=[item.dict() for item in body.items], meta=body.meta)
    """批量接受 VPPS 描述别名，并在 meta 中记录来源信息。"""
    user_name = current_user.get("name") or current_user.get("email") or current_user.get("sub", "?")
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    processed = 0
    failed = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for item in body.items:
                try:
                    alias = item.alias
                    note = f'[别名] {user_name} @ {now_str}: 接受别名"{alias}"'
                    alias_record = json.dumps(
                        [{**body.meta, "alias": alias, "accepted_by": user_name, "accepted_at": now_str}],
                        ensure_ascii=False
                    )
                    cur.execute(
                        "UPDATE workmanship_tpl_vpps_parts "
                        "SET alias = CASE WHEN JSON_CONTAINS(alias, %s) THEN alias ELSE JSON_MERGE_PATCH(alias, %s) END, "
                        "meta = JSON_SET("
                        "  IFNULL(meta, '{}'),"
                        "  '$.alias_records',"
                        "  CAST(CONCAT('[', TRIM(LEADING '[' FROM TRIM(TRAILING ']' FROM IFNULL(JSON_EXTRACT(meta,'$.alias_records'),'[]'))), IF(JSON_LENGTH(IFNULL(JSON_EXTRACT(meta,'$.alias_records'),'[]'))>0,',',''), %s, ']') AS JSON)"
                        ") "
                        "WHERE gid = %s",
                        (json.dumps([alias]), json.dumps([alias]), alias_record, item.vpps_part_gid),
                    )
                    if item.pbom_part_gid:
                        cur.execute(
                            "UPDATE workmanship_bop_pbom SET remark = "
                            "CASE WHEN remark = '' OR remark IS NULL THEN %s ELSE remark || '; ' || %s END "
                            "WHERE gid = %s",
                            (note, note, item.pbom_part_gid),
                        )
                    processed += 1
                except Exception:
                    _log.warning("craft_library batch_accept: 单条处理失败", exc_info=True)
                    failed += 1
        conn.commit()
    return {"success": True, "processed": processed, "failed": failed}




@router.post("/part_names/{gid}/accept_alias")
async def accept_vpps_alias(gid: str, body: AcceptAliasBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_change(request, current_user, principal, gateway, "part_names.accept_alias", gid=gid, alias=body.alias, record={"pbom_part_gid": body.pbom_part_gid})
    user_name = current_user.get("name") or current_user.get("email") or current_user.get("sub", "?")
    now_str   = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    note = f'[别名] {user_name} @ {now_str}: 接受别名"{body.alias}"'
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 幂等追加：若已存在则不重复
            cur.execute(
                "UPDATE workmanship_tpl_vpps_parts "
                "SET alias = CASE WHEN JSON_CONTAINS(alias, %s) THEN alias ELSE JSON_MERGE_PATCH(alias, %s) END "
                "WHERE gid = %s",
                (json.dumps([body.alias]), json.dumps([body.alias]), gid)
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "VPPS零件不存在")
            # 更新 PBOM 行 remark（pbom_part_gid 非空才更新）
            if body.pbom_part_gid:
                cur.execute(
                    "UPDATE workmanship_bop_pbom SET remark = "
                    "CASE WHEN remark = '' OR remark IS NULL THEN %s ELSE remark || '; ' || %s END "
                    "WHERE gid = %s",
                    (note, note, body.pbom_part_gid)
                )
        conn.commit()
    return {"success": True}
