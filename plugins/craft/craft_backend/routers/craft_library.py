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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, require_role
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/craft_lib", tags=["craft_library"])
_log = __import__('logging').getLogger(__name__)

_READ = require_role("super_admin", "team_admin", "project_admin",
                     "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "knowledge_admin")


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


_alias_migrated = False

def _ensure_alias_column():
    global _alias_migrated
    if _alias_migrated: return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "ALTER TABLE workmanship_tpl_vpps_parts "
                        "ADD COLUMN alias JSON NOT NULL DEFAULT (JSON_ARRAY())"
                    )
                except Exception as e:
                    if not (getattr(e, "args", None) and len(e.args) > 0 and e.args[0] == 1060):
                        raise
            conn.commit()
        _alias_migrated = True
    except Exception as e:
        print(f"[craft_lib] alias column migration error: {e}")


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
def list_tools(current_user: dict = Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_TOOL_COLS} FROM workmanship_tpl_vpps_tools ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "vpps": r["vpps"], "name": r["name"],
         "gun_model": r["gun_model"], "matou_part_no": r["matou_part_no"],
         "importance": r["importance"], "gun_type": r["gun_type"],
         "wireless": r["wireless"], "output_square": r["output_square"],
         "torque_min": r["torque_min"], "torque_recommended": r["torque_recommended"],
         "cad_model_no": r["cad_model_no"], "socket_model": r["socket_model"],
         "fastener_type": r["fastener_type"], "fastener_params": r["fastener_params"],
         "extension_model": r["extension_model"], "socket_cad_no": r["socket_cad_no"],
         "extension_cad_no": r["extension_cad_no"], "status": r["status"],
         "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.post("/tools", status_code=201)
def create_tool(body: ToolBody, current_user: dict = Depends(_WRITE)):
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
def delete_tool(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_tpl_vpps_tools WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="工具模板不存在")
        conn.commit()
    return {"success": True}


@router.patch("/tools/{gid}")
def update_tool(gid: str, body: ToolBody, current_user: dict = Depends(_WRITE)):
    allowed = ["vpps","name","gun_model","matou_part_no","importance","gun_type",
               "wireless","output_square","torque_min","torque_recommended","cad_model_no",
               "socket_model","fastener_type","fastener_params","extension_model",
               "socket_cad_no","extension_cad_no"]
    return _patch_record("workmanship_tpl_vpps_tools", gid, body, allowed)


@router.post("/tools/{gid}/obsolete")
def obsolete_tool(gid: str, current_user: dict = Depends(_WRITE)):
    return _obsolete_template("workmanship_tpl_vpps_tools", gid, current_user)


# ── 设备模板 ──────────────────────────────────────────────────────

@router.get("/equipments")
def list_equipments(current_user: dict = Depends(_READ)):
    return _list_template("workmanship_tpl_vpps_equipments", current_user)


@router.post("/equipments", status_code=201)
def create_equipment(body: TemplateBody, current_user: dict = Depends(_WRITE)):
    return _create_template("workmanship_tpl_vpps_equipments", body, current_user)


@router.post("/equipments/{gid}/obsolete")
def obsolete_equipment(gid: str, current_user: dict = Depends(_WRITE)):
    return _obsolete_template("workmanship_tpl_vpps_equipments", gid, current_user)


@router.patch("/equipments/{gid}")
def update_equipment(gid: str, body: UpdateTemplateBody, current_user: dict = Depends(_WRITE)):
    return _patch_record("workmanship_tpl_vpps_equipments", gid, body, ["name", "category", "spec"])


# ── 工装模板 ──────────────────────────────────────────────────────

@router.get("/fixtures")
def list_fixtures(current_user: dict = Depends(_READ)):
    return _list_template("workmanship_tpl_vpps_fixtures", current_user)


@router.post("/fixtures", status_code=201)
def create_fixture(body: TemplateBody, current_user: dict = Depends(_WRITE)):
    return _create_template("workmanship_tpl_vpps_fixtures", body, current_user)


@router.post("/fixtures/{gid}/obsolete")
def obsolete_fixture(gid: str, current_user: dict = Depends(_WRITE)):
    return _obsolete_template("workmanship_tpl_vpps_fixtures", gid, current_user)


@router.patch("/fixtures/{gid}")
def update_fixture(gid: str, body: UpdateTemplateBody, current_user: dict = Depends(_WRITE)):
    return _patch_record("workmanship_tpl_vpps_fixtures", gid, body, ["name", "category", "spec"])


# ── 标准紧固件 ────────────────────────────────────────────────────

_FASTENER_COLS = ("gid, fastener_type, part_no, name, thread_spec, model, "
                  "shank_length, guide_type, guide_length, has_adhesive, "
                  "drive_size, flange_diameter, first_vehicle, status, created_at")


@router.get("/fasteners")
def list_fasteners(current_user: dict = Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_FASTENER_COLS} FROM workmanship_tpl_fastener_spec ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "fastener_type": r["fastener_type"], "part_no": r["part_no"],
         "name": r["name"], "thread_spec": r["thread_spec"], "model": r["model"],
         "shank_length": r["shank_length"], "guide_type": r["guide_type"],
         "guide_length": r["guide_length"], "has_adhesive": r["has_adhesive"],
         "drive_size": r["drive_size"], "flange_diameter": r["flange_diameter"],
         "first_vehicle": r["first_vehicle"], "status": r["status"],
         "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.post("/fasteners", status_code=201)
def create_fastener(body: FastenerBody, current_user: dict = Depends(_WRITE)):
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
def delete_fastener(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_tpl_fastener_spec WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="紧固件不存在")
        conn.commit()
    return {"success": True}


@router.patch("/fasteners/{gid}")
def update_fastener(gid: str, body: UpdateFastenerBody, current_user: dict = Depends(_WRITE)):
    return _patch_record("workmanship_tpl_fastener_spec", gid, body,
                         ["fastener_type", "part_no", "name", "thread_spec", "model",
                          "shank_length", "guide_type", "guide_length", "has_adhesive",
                          "drive_size", "flange_diameter", "first_vehicle"])


# ── 标准零件名 ────────────────────────────────────────────────────

@router.get("/part_names")
def list_part_names(
    q: Optional[str] = Query(None),
    current_user: dict = Depends(_READ)
):
    _ensure_alias_column()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if q:
                cur.execute(
                    "SELECT gid, vpps_description, part_category, description, "
                    "level, vpps_desc_cn, vpps, importance, vehicle_model, parent_vpps, status, meta, "
                    "flex_type, ref_main_vpps, ref_main_vpps_desc, "
                    "ref_install_direction, ref_static_clearance, ref_install_clearance, alias, created_at "
                    "FROM workmanship_tpl_vpps_parts WHERE vpps_description LIKE %s ORDER BY vpps_description",
                    (f"%{q}%",)
                )
            else:
                cur.execute(
                    "SELECT gid, vpps_description, part_category, description, "
                    "level, vpps_desc_cn, vpps, importance, vehicle_model, parent_vpps, status, meta, "
                    "flex_type, ref_main_vpps, ref_main_vpps_desc, "
                    "ref_install_direction, ref_static_clearance, ref_install_clearance, alias, created_at "
                    "FROM workmanship_tpl_vpps_parts ORDER BY vpps_description"
                )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {"gid": r["gid"], "vpps_description": r["vpps_description"], "part_category": r["part_category"],
         "description": r["description"], "level": r["level"], "vpps_desc_cn": r["vpps_desc_cn"],
         "vpps": r["vpps"], "importance": r["importance"], "vehicle_model": r["vehicle_model"],
         "parent_vpps": r["parent_vpps"], "status": r["status"], "meta": r["meta"] or {},
         "flex_type": r["flex_type"], "ref_main_vpps": r["ref_main_vpps"],
         "ref_main_vpps_desc": r["ref_main_vpps_desc"],
         "ref_install_direction": r["ref_install_direction"],
         "ref_static_clearance": r["ref_static_clearance"],
         "ref_install_clearance": r["ref_install_clearance"],
         "alias": list(r["alias"] or []),
         "created_at": str(r["created_at"])}
        for r in rows
    ]}


@router.post("/part_names", status_code=201)
def create_part_name(body: PartNameBody, current_user: dict = Depends(_WRITE)):
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
                "ref_install_direction, ref_static_clearance, ref_install_clearance) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, body.vpps_description, body.part_category, body.description,
                 body.level, body.vpps_desc_cn, body.vpps,
                 body.importance, body.vehicle_model, body.parent_vpps, body.status,
                 json.dumps(body.meta, ensure_ascii=False),
                 current_user.get("team_id"),
                 body.flex_type, body.ref_main_vpps, body.ref_main_vpps_desc,
                 body.ref_install_direction, body.ref_static_clearance, body.ref_install_clearance)
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.delete("/part_names/{gid}")
def delete_part_name(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_tpl_vpps_parts WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="零件名不存在")
        conn.commit()
    return {"success": True}


@router.patch("/part_names/{gid}")
def update_part_name(gid: str, body: PartNameBody, current_user: dict = Depends(_WRITE)):
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
def batch_add_part_names_from_pbom(body: BatchAddFromPbomBody, current_user: dict = Depends(_WRITE)):
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
def batch_accept_vpps_alias(body: BatchAcceptAliasBody, current_user: dict = Depends(_WRITE)):
    """批量接受 VPPS 描述别名，并在 meta 中记录来源信息。"""
    _ensure_alias_column()
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
def accept_vpps_alias(gid: str, body: AcceptAliasBody, current_user: dict = Depends(_WRITE)):
    _ensure_alias_column()
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
