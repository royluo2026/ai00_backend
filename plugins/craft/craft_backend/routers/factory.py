"""
backend/routers/factory.py
────────────────────────────
工厂资源 API（factory_tools / factory_equipments / factory_fixtures / factory_sections / factory_stations）

端点前缀：/api/factory
  GET  /tools                    → 工具资产列表
  POST /tools                    → 登记工具资产
  DELETE /tools/{gid}            → 删除工具资产
  POST /tools/{gid}/maintenance  → 送修
  POST /tools/{gid}/return       → 归还
  POST /tools/{gid}/scrap        → 报废

  (同样适用于 /equipments, /fixtures)

  GET  /sections                 → 工段列表
  POST /sections                 → 新建工段
  DELETE /sections/{gid}         → 删除工段

  GET  /stations                 → 工位列表
  POST /stations                 → 新建工位
  DELETE /stations/{gid}         → 删除工位
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user, require_role
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/factory", tags=["factory"])

_READ = require_role("super_admin", "team_admin", "project_admin",
                     "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "project_admin")


class RegisterAssetBody(BaseModel):
    asset_no: str
    template_gid: Optional[str] = None
    meta: dict = {}


class SectionBody(BaseModel):
    name: str
    factory_gid: str
    sort_order: int = 0
    color: str = "#7287fd"


class StationBody(BaseModel):
    code: str = ""
    name: str = ""
    factory_section_gid: str
    takt_time: float = 60
    height_mm: int = 1200
    meta: dict = {}


class UpdateAssetBody(BaseModel):
    asset_no: Optional[str] = None
    template_gid: Optional[str] = None
    meta: Optional[dict] = None


class UpdateSectionBody(BaseModel):
    name: Optional[str] = None
    factory_gid: Optional[str] = None
    sort_order: Optional[int] = None
    color: Optional[str] = None


class UpdateStationBody(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    factory_section_gid: Optional[str] = None
    takt_time: Optional[float] = None
    height_mm: Optional[int] = None
    meta: Optional[dict] = None


def _list_assets(table: str, current_user: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT gid, asset_no, template_gid, status, meta, created_at, updated_at "
                f"FROM {table} ORDER BY updated_at DESC"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "asset_no": r["asset_no"], "template_gid": r["template_gid"],
         "status": r["status"], "meta": r["meta"] or {},
         "created_at": str(r["created_at"]), "updated_at": str(r["updated_at"])}
        for r in rows
    ]}


def _register_asset(table: str, body: RegisterAssetBody, current_user: dict):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {table} (gid, asset_no, template_gid, meta, team_id) "
                f"VALUES (%s, %s, %s, %s, %s)",
                (gid, body.asset_no, body.template_gid,
                 json.dumps(body.meta, ensure_ascii=False),
                 current_user.get("team_id"))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "asset_no": body.asset_no}}


def _delete_asset(table: str, gid: str, current_user: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table} WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="资产不存在")
        conn.commit()
    return {"success": True}


def _update_asset_status(table: str, gid: str, new_status: str,
                          allowed_from: list, current_user: dict):
    cond = ", ".join(["%s"] * len(allowed_from))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET status = %s, updated_at = NOW() "
                f"WHERE gid = %s AND status IN ({cond})",
                [new_status, gid] + list(allowed_from)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=400, detail="资产不存在或状态不符")
        conn.commit()
    return {"success": True}


# ── 工具资产 ──────────────────────────────────────────────────────

@router.get("/tools")
def list_tools(current_user: dict = Depends(_READ)):
    return _list_assets("workmanship_factory_factory_tools", current_user)


@router.post("/tools", status_code=201)
def register_tool(body: RegisterAssetBody, current_user: dict = Depends(_WRITE)):
    return _register_asset("workmanship_factory_factory_tools", body, current_user)


@router.delete("/tools/{gid}")
def delete_tool(gid: str, current_user: dict = Depends(_WRITE)):
    return _delete_asset("workmanship_factory_factory_tools", gid, current_user)


@router.post("/tools/{gid}/maintenance")
def tool_to_maintenance(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_tools", gid, "maintenance", ["in_use"], current_user)


@router.post("/tools/{gid}/return")
def tool_return(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_tools", gid, "in_use", ["maintenance"], current_user)


@router.post("/tools/{gid}/scrap")
def tool_scrap(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_tools", gid, "scrapped", ["in_use", "maintenance"], current_user)


# ── 设备资产 ──────────────────────────────────────────────────────

@router.get("/equipments")
def list_equipments(current_user: dict = Depends(_READ)):
    return _list_assets("workmanship_factory_factory_equipments", current_user)


@router.post("/equipments", status_code=201)
def register_equipment(body: RegisterAssetBody, current_user: dict = Depends(_WRITE)):
    return _register_asset("workmanship_factory_factory_equipments", body, current_user)


@router.delete("/equipments/{gid}")
def delete_equipment(gid: str, current_user: dict = Depends(_WRITE)):
    return _delete_asset("workmanship_factory_factory_equipments", gid, current_user)


@router.post("/equipments/{gid}/maintenance")
def equipment_to_maintenance(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_equipments", gid, "maintenance", ["in_use"], current_user)


@router.post("/equipments/{gid}/return")
def equipment_return(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_equipments", gid, "in_use", ["maintenance"], current_user)


@router.post("/equipments/{gid}/scrap")
def equipment_scrap(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_equipments", gid, "scrapped", ["in_use", "maintenance"], current_user)


# ── 工装资产 ──────────────────────────────────────────────────────

@router.get("/fixtures")
def list_fixtures(current_user: dict = Depends(_READ)):
    return _list_assets("workmanship_factory_factory_fixtures", current_user)


@router.post("/fixtures", status_code=201)
def register_fixture(body: RegisterAssetBody, current_user: dict = Depends(_WRITE)):
    return _register_asset("workmanship_factory_factory_fixtures", body, current_user)


@router.delete("/fixtures/{gid}")
def delete_fixture(gid: str, current_user: dict = Depends(_WRITE)):
    return _delete_asset("workmanship_factory_factory_fixtures", gid, current_user)


@router.post("/fixtures/{gid}/maintenance")
def fixture_to_maintenance(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_fixtures", gid, "maintenance", ["in_use"], current_user)


@router.post("/fixtures/{gid}/return")
def fixture_return(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_fixtures", gid, "in_use", ["maintenance"], current_user)


@router.post("/fixtures/{gid}/scrap")
def fixture_scrap(gid: str, current_user: dict = Depends(_WRITE)):
    return _update_asset_status("workmanship_factory_factory_fixtures", gid, "scrapped", ["in_use", "maintenance"], current_user)


# ── 工段 ─────────────────────────────────────────────────────────

@router.get("/sections")
def list_sections(current_user: dict = Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, factory_gid, sort_order, color, created_at "
                "FROM workmanship_factory_factory_sections ORDER BY sort_order, created_at"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "name": r["name"], "factory_gid": r["factory_gid"],
         "sort_order": r["sort_order"], "color": r["color"],
         "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.post("/sections", status_code=201)
def create_section(body: SectionBody, current_user: dict = Depends(_WRITE)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_factory_factory_sections (gid, name, factory_gid, sort_order, color) "
                "VALUES (%s, %s, %s, %s, %s)",
                (gid, body.name, body.factory_gid, body.sort_order, body.color)
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "name": body.name}}


@router.delete("/sections/{gid}")
def delete_section(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_factory_factory_sections WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="工段不存在")
        conn.commit()
    return {"success": True}


# ── 工位 ─────────────────────────────────────────────────────────

@router.get("/stations")
def list_stations(current_user: dict = Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, code, name, factory_section_gid, takt_time, height_mm, meta, created_at "
                "FROM workmanship_factory_factory_stations ORDER BY code, created_at"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "code": r["code"], "name": r["name"],
         "factory_section_gid": r["factory_section_gid"],
         "takt_time": r["takt_time"], "height_mm": r["height_mm"],
         "meta": r["meta"] or {}, "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.post("/stations", status_code=201)
def create_station(body: StationBody, current_user: dict = Depends(_WRITE)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_factory_factory_stations "
                "(gid, code, name, factory_section_gid, takt_time, height_mm, meta) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (gid, body.code, body.name, body.factory_section_gid,
                 body.takt_time, body.height_mm,
                 json.dumps(body.meta, ensure_ascii=False))
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "code": body.code}}


@router.delete("/stations/{gid}")
def delete_station(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_factory_factory_stations WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="工位不存在")
        conn.commit()
    return {"success": True}


# ── PATCH 端点（编辑更新） ────────────────────────────────────────

def _patch_factory(table: str, gid: str, body, allowed: list):
    fields = body.dict(exclude_unset=True)
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return {"success": True}
    # meta 字段需要 JSON 转换
    params = []
    set_parts = []
    for k, v in fields.items():
        if k == "meta":
            set_parts.append(f"{k} = %s")
            params.append(json.dumps(v, ensure_ascii=False))
        else:
            set_parts.append(f"{k} = %s")
            params.append(v)
    params.append(gid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET {', '.join(set_parts)} WHERE gid = %s", params
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="记录不存在")
        conn.commit()
    return {"success": True}


@router.patch("/tools/{gid}")
def patch_tool(gid: str, body: UpdateAssetBody, current_user: dict = Depends(_WRITE)):
    return _patch_factory("workmanship_factory_factory_tools", gid, body, ["asset_no", "template_gid", "meta"])


@router.patch("/equipments/{gid}")
def patch_equipment(gid: str, body: UpdateAssetBody, current_user: dict = Depends(_WRITE)):
    return _patch_factory("workmanship_factory_factory_equipments", gid, body, ["asset_no", "template_gid", "meta"])


@router.patch("/fixtures/{gid}")
def patch_fixture(gid: str, body: UpdateAssetBody, current_user: dict = Depends(_WRITE)):
    return _patch_factory("workmanship_factory_factory_fixtures", gid, body, ["asset_no", "template_gid", "meta"])


@router.patch("/sections/{gid}")
def patch_section(gid: str, body: UpdateSectionBody, current_user: dict = Depends(_WRITE)):
    return _patch_factory("workmanship_factory_factory_sections", gid, body, ["name", "factory_gid", "sort_order", "color"])


@router.patch("/stations/{gid}")
def patch_station(gid: str, body: UpdateStationBody, current_user: dict = Depends(_WRITE)):
    return _patch_factory("workmanship_factory_factory_stations", gid, body,
                          ["code", "name", "factory_section_gid", "takt_time", "height_mm", "meta"])
