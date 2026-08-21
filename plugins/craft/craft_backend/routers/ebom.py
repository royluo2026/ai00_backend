"""
Native PBOM HTTP transport (legacy module filename retained until route-loader cutover).
─────────────────────────
PBOM API（pbom_versions / pbom）

端点：
  GET/POST /api/pbom/versions                    → 版本查询/创建
  GET/DELETE /api/pbom/versions/{gid}            → 版本详情/归档
  GET/POST /api/pbom/versions/{gid}/parts        → 零件查询/变更
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user, require_role
from backend.platform_sdk.ids import next_gid
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from uuid import uuid4

# Compatibility path stays mounted until the production consumer-cutover task;
# all native Provider contracts use PBOM naming now.
router = APIRouter(prefix="/api/ebom", tags=["pbom"])
_log = __import__('logging').getLogger(__name__)

_READ = require_role("super_admin", "team_admin", "project_admin",
                     "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "project_admin", "member")

# ── 版本列全集 ───────────────────────────────────────────────────
_VER_COLS = "gid, project_gid, version_tag, name, source_type, status, created_at"

# ── 零件列全集（对齐 TC/PLM 导出 Excel 19 列 + 系统字段）────────
_PART_COLS = (
    "gid, snapshot_gid, part_no, title AS name, quantity, unit, material, parent_gid, "
    "vpps, vpps_desc, parent_vpps, parent_vpps_name, bom_row, bom_row_label, component_id, "
    "component_type, component_version_status, purchase_status, "
    "variable_formula, torque, torque_importance, ownership_user, "
    "level, home, configuration, parent_bom_row, remark, temp_vpps, "
    "catia_occurrence_name, catia_file_name, catia_uuid, "
    "default_matrix, abs_matrix, rel_matrix, local_bbox, ecn, fna, "
    "geo_main_part, ref_main_vpps_desc, ref_main_vpps, "
    "main_part_consistency, geo_evidence, lr_side, meta, created_at"
)

def _row_to_ver(r):
    return {
        "gid": r["gid"], "project_gid": r["project_gid"],
        "version_tag": r["version_tag"], "name": r.get("name", ""),
        "source_type": r["source_type"], "status": r["status"],
        "created_at": str(r["created_at"]),
    }

def _row_to_part(r):
    return {
        "gid": r["gid"], "snapshot_gid": r["snapshot_gid"],
        "part_no": r["part_no"], "name": r["name"],
        "quantity": r["quantity"], "unit": r["unit"],
        "material": r["material"], "parent_gid": r["parent_gid"],
        "vpps": r.get("vpps"), "vpps_desc": r.get("vpps_desc", ""),
        "parent_vpps": r.get("parent_vpps", ""),
        "parent_vpps_name": r.get("parent_vpps_name", ""),
        "bom_row": r.get("bom_row", ""),
        "bom_row_label": r.get("bom_row_label", ""),
        "component_id": r.get("component_id", ""),
        "component_type": r.get("component_type", ""),
        "component_version_status": r.get("component_version_status", ""),
        "purchase_status": r.get("purchase_status", ""),
        "variable_formula": r.get("variable_formula", ""),
        "torque": r.get("torque", ""),
        "torque_importance": r.get("torque_importance", ""),
        "ownership_user": r.get("ownership_user", ""),
        "level": r.get("level"),
        "home": r.get("home", ""),
        "configuration": r.get("configuration", ""),
        "parent_bom_row": r.get("parent_bom_row", ""),
        "remark": r.get("remark", ""),
        "temp_vpps": r.get("temp_vpps", ""),
        "catia_occurrence_name": r.get("catia_occurrence_name", ""),
        "catia_file_name": r.get("catia_file_name", ""),
        "catia_uuid": r.get("catia_uuid", ""),
        "default_matrix": r.get("default_matrix", ""),
        "abs_matrix": r.get("abs_matrix", ""),
        "rel_matrix": r.get("rel_matrix", ""),
        "local_bbox": r.get("local_bbox", ""),
        "ecn": r.get("ecn", ""),
        "fna": r.get("fna", ""),
        "geo_main_part": r.get("geo_main_part", ""),
        "ref_main_vpps_desc": r.get("ref_main_vpps_desc", ""),
        "ref_main_vpps": r.get("ref_main_vpps", ""),
        "main_part_consistency": r.get("main_part_consistency", ""),
        "geo_evidence": r.get("geo_evidence", ""),
        "lr_side": r.get("lr_side", ""),
        "meta": r.get("meta", {}),
        "created_at": str(r["created_at"]),
    }


# ── Pydantic Models ──────────────────────────────────────────────

class CreateVersionBody(BaseModel):
    project_gid: Optional[str] = None
    version_tag: str = ""
    name: str = ""
    source_type: str = "manual"


class CreatePartBody(BaseModel):
    part_no: str = ""
    name: str = ""
    quantity: float = 1
    unit: str = "pcs"
    material: Optional[str] = None
    parent_gid: Optional[str] = None
    vpps: Optional[str] = None
    vpps_desc: Optional[str] = ""
    parent_vpps: Optional[str] = ""
    parent_vpps_name: Optional[str] = ""
    bom_row: Optional[str] = ""
    bom_row_label: Optional[str] = ""
    component_id: Optional[str] = ""
    component_type: Optional[str] = ""
    component_version_status: Optional[str] = ""
    purchase_status: Optional[str] = ""
    variable_formula: Optional[str] = ""
    torque: Optional[str] = ""
    torque_importance: Optional[str] = ""
    ownership_user: Optional[str] = ""
    level: Optional[int] = None
    home: Optional[str] = ""
    configuration: Optional[str] = ""
    parent_bom_row: Optional[str] = ""
    remark: Optional[str] = None
    temp_vpps: Optional[str] = None
    catia_occurrence_name: Optional[str] = ""
    catia_file_name: Optional[str] = ""
    catia_uuid: Optional[str] = ""
    default_matrix: Optional[str] = ""
    abs_matrix: Optional[str] = ""
    rel_matrix: Optional[str] = ""
    local_bbox: Optional[str] = ""
    ecn: Optional[str] = ""
    fna: Optional[str] = ""
    geo_main_part: Optional[str] = ""
    ref_main_vpps_desc: Optional[str] = ""
    ref_main_vpps: Optional[str] = ""
    main_part_consistency: Optional[str] = ""
    geo_evidence: Optional[str] = ""
    lr_side: Optional[str] = ""


class UpdatePartBody(BaseModel):
    part_no: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    material: Optional[str] = None
    vpps: Optional[str] = None
    vpps_desc: Optional[str] = None
    parent_vpps: Optional[str] = None
    parent_vpps_name: Optional[str] = None
    bom_row: Optional[str] = None
    bom_row_label: Optional[str] = None
    component_id: Optional[str] = None
    component_type: Optional[str] = None
    component_version_status: Optional[str] = None
    purchase_status: Optional[str] = None
    variable_formula: Optional[str] = None
    torque: Optional[str] = None
    torque_importance: Optional[str] = None
    ownership_user: Optional[str] = None
    level: Optional[int] = None
    home: Optional[str] = None
    configuration: Optional[str] = None
    parent_bom_row: Optional[str] = None
    remark: Optional[str] = None
    temp_vpps: Optional[str] = None
    catia_occurrence_name: Optional[str] = None
    catia_file_name: Optional[str] = None
    catia_uuid: Optional[str] = None
    default_matrix: Optional[str] = None
    abs_matrix: Optional[str] = None
    rel_matrix: Optional[str] = None
    local_bbox: Optional[str] = None
    ecn: Optional[str] = None
    fna: Optional[str] = None
    geo_main_part: Optional[str] = None
    ref_main_vpps_desc: Optional[str] = None
    ref_main_vpps: Optional[str] = None
    main_part_consistency: Optional[str] = None
    geo_evidence: Optional[str] = None
    lr_side: Optional[str] = None


async def _invoke_pbom(request: Request, current_user: dict, principal, gateway, capability_id: str, payload: dict, *, write: bool = False):
    request_id = request.headers.get("X-Request-ID") or f"craft_pbom_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway,
        capability_id=capability_id,
        payload=payload,
        current_user=current_user,
        principal=principal,
        request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=(request.headers.get("X-Idempotency-Key") or request_id) if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400, "version_conflict": 409}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


async def _invoke_ebom_change(request: Request, current_user: dict, principal, gateway, payload: dict):
    return await _invoke_pbom(request, current_user, principal, gateway, capability_id="craft.ebom.change.apply", payload=payload, write=True)


async def _invoke_ebom_atomic(request: Request, current_user: dict, principal, gateway, capability_id: str, payload: dict):
    return await _invoke_pbom(request, current_user, principal, gateway, capability_id=capability_id, payload=payload, write=True)


def _legacy_version(item: dict) -> dict:
    version_tag = item.get("version_tag") or ""
    return {
        "gid": item.get("gid", ""),
        "project_gid": item.get("project_gid") or item.get("project_ref"),
        "version_tag": version_tag,
        "name": item.get("name") or version_tag,
        "source_type": item.get("source_type") or "native",
        "status": item.get("status", "draft"),
        "created_at": item.get("created_at") or "",
    }


# ── 版本端点 ─────────────────────────────────────────────────────

@router.get("/snapshots")
async def list_snapshots(
    project_gid: Optional[str] = Query(None),
    request: Request = None,
    current_user: dict = Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    data = await _invoke_pbom(request, current_user, principal, gateway, "craft.pbom.version.search", {
        "project_ref": project_gid,
        "limit": 200,
    })
    return {"success": True, "data": [_legacy_version(item) for item in data.get("items", [])]}


@router.post("/snapshots", status_code=201)
async def create_snapshot(
    body: CreateVersionBody,
    request: Request = None,
    current_user: dict = Depends(_WRITE),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    data = await _invoke_pbom(request, current_user, principal, gateway, "craft.pbom.version.create", {
        "project_ref": body.project_gid or "",
        "project_gid": body.project_gid,
        "version_tag": body.version_tag,
        "name": body.name,
        "source_type": body.source_type,
    }, write=True)
    return {"success": True, "data": {"gid": data.get("gid", "")}}


@router.get("/snapshots/{gid}")
async def get_snapshot(
    gid: str,
    request: Request = None,
    current_user: dict = Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    data = await _invoke_pbom(request, current_user, principal, gateway, "craft.pbom.version.get", {"version_gid": gid})
    return {"success": True, "data": _legacy_version(data) | {"meta": data.get("meta") or {}}}


@router.delete("/snapshots/{gid}")
async def delete_snapshot(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.snapshot.delete", {"snapshot_gid": gid})


def _legacy_delete_snapshot(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_bop_pbom_versions WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="PBOM 版本不存在")
        conn.commit()
    return {"success": True}


_ALLOWED_STATUSES = {"raw", "ready", "draft"}

_PBOM_PATCH_ALLOWED = {"name", "version_tag", "visibility", "shared_team_gid", "shared_project_gid"}

class PatchSnapshotBody(BaseModel):
    name:               Optional[str] = None
    version_tag:        Optional[str] = None
    visibility:         Optional[str] = None
    shared_team_gid:    Optional[str] = None
    shared_project_gid: Optional[str] = None

@router.patch("/snapshots/{gid}")
async def patch_snapshot(gid: str, body: PatchSnapshotBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.snapshot.update", {"snapshot_gid": gid, "changes": body.model_dump(exclude_none=True)})


def _legacy_patch_snapshot(gid: str, body: PatchSnapshotBody, current_user: dict = Depends(_WRITE)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k in _PBOM_PATCH_ALLOWED}
    if not updates:
        raise HTTPException(status_code=400, detail="无更新字段")
    with get_conn() as conn:
        with conn.cursor() as cur:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            cur.execute(f"UPDATE workmanship_bop_pbom_versions SET {set_clause} WHERE gid = %s", list(updates.values()) + [gid])
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="PBOM版本不存在")
        conn.commit()
    return {"success": True}


class VppsStatsBody(BaseModel):
    nok:     int = 0
    ignored: int = 0
    total:   int = 0


@router.patch("/snapshots/{gid}/vpps-stats", status_code=200)
async def patch_vpps_stats(gid: str, body: VppsStatsBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.snapshot.vpps_stats.update", {"snapshot_gid": gid, **body.model_dump()})


def _legacy_patch_vpps_stats(gid: str, body: VppsStatsBody, current_user: dict = Depends(_WRITE)):
    """将 VPPS 核对结果写入 pbom_versions.meta.vpps_check，供生命周期面板读取。"""
    import json as _json
    from datetime import datetime, timezone
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT meta FROM workmanship_bop_pbom_versions WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "PBOM版本不存在")
            meta = dict(row)['meta'] or {}
            meta['vpps_check'] = {
                'nok':        body.nok,
                'ignored':    body.ignored,
                'total':      body.total,
                'checked_at': datetime.now(timezone.utc).isoformat(),
            }
            cur.execute(
                "UPDATE workmanship_bop_pbom_versions SET meta=%s WHERE gid=%s",
                (_json.dumps(meta), gid)
            )
            conn.commit()
    return {"success": True, "vpps_check": meta['vpps_check']}

class PatchVersionStatusBody(BaseModel):
    status: str

@router.patch("/snapshots/{gid}/status")
async def patch_snapshot_status(
    gid: str,
    body: PatchVersionStatusBody,
    request: Request,
    current_user: dict = Depends(_WRITE),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.snapshot.status.update", {"snapshot_gid": gid, "status": body.status})


def _legacy_patch_snapshot_status(
    gid: str,
    body: PatchVersionStatusBody,
    current_user: dict = Depends(_WRITE),
):
    if body.status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"无效状态值，允许：{_ALLOWED_STATUSES}")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_bop_pbom_versions SET status = %s WHERE gid = %s",
                (body.status, gid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="PBOM 版本不存在")
        conn.commit()
    return {"success": True, "data": {"gid": gid, "status": body.status}}


# ── 零件端点 ─────────────────────────────────────────────────────

@router.get("/snapshots/{gid}/parts")
async def list_parts(
    gid: str,
    limit: int = Query(500, ge=1, le=500),
    request: Request = None,
    current_user: dict = Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    data = await _invoke_pbom(request, current_user, principal, gateway, "craft.pbom.part.search", {
        "version_gid": gid,
        "limit": limit,
    })
    rows = []
    for item in data.get("items", []):
        row = dict(item)
        row.setdefault("name", row.get("title", ""))
        rows.append(_row_to_part(row))
    return {"success": True, "data": rows}


_INSERT_PART_SQL = (
    "INSERT INTO workmanship_bop_pbom "
    "(gid, snapshot_gid, part_no, title, quantity, unit, material, parent_gid, "
    "vpps, vpps_desc, parent_vpps, parent_vpps_name, bom_row, bom_row_label, component_id, "
    "component_type, component_version_status, purchase_status, "
    "variable_formula, torque, torque_importance, ownership_user, "
    "level, home, configuration, parent_bom_row, remark, temp_vpps, "
    "catia_occurrence_name, catia_file_name, catia_uuid, "
    "default_matrix, abs_matrix, rel_matrix, local_bbox, ecn, fna, "
    "geo_main_part, ref_main_vpps_desc, ref_main_vpps, "
    "main_part_consistency, geo_evidence, lr_side, "
    "vpps_source, is_deleted, meta) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

def _part_vals(part_gid, snap_gid, b):
    return (
        part_gid, snap_gid, b.part_no, b.name, b.quantity, b.unit,
        b.material, b.parent_gid,
        b.vpps, b.vpps_desc or '', b.parent_vpps or '', b.parent_vpps_name or '',
        b.bom_row or '', b.bom_row_label or '', b.component_id or '',
        b.component_type or '', b.component_version_status or '',
        b.purchase_status or '', b.variable_formula or '',
        b.torque or '', b.torque_importance or '', b.ownership_user or '',
        b.level, b.home or '', b.configuration or '', b.parent_bom_row or '',
        b.remark or '', b.temp_vpps or '',
        b.catia_occurrence_name or '', b.catia_file_name or '', b.catia_uuid or '',
        b.default_matrix or '', b.abs_matrix or '', b.rel_matrix or '',
        b.local_bbox or '', b.ecn or '', b.fna or '',
        b.geo_main_part or '', b.ref_main_vpps_desc or '', b.ref_main_vpps or '',
        b.main_part_consistency or '', b.geo_evidence or '', b.lr_side or '',
        'auto', 0, '{}',   # vpps_source, is_deleted, meta
    )


@router.post("/snapshots/{gid}/parts", status_code=201)
async def add_part(gid: str, body: CreatePartBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.part.create", {"snapshot_gid": gid, "part": body.model_dump()})


def _legacy_add_part(gid: str, body: CreatePartBody, current_user: dict = Depends(_WRITE)):
    part_gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_bop_pbom_versions WHERE gid = %s", (gid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="PBOM 版本不存在")
            cur.execute(_INSERT_PART_SQL, _part_vals(part_gid, gid, body))
        conn.commit()
    return {"success": True, "data": {"gid": part_gid}}


@router.post("/snapshots/{gid}/parts/batch", status_code=201)
async def add_parts_batch(gid: str, body: List[CreatePartBody], request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.part.bulk_create", {"snapshot_gid": gid, "parts": [item.model_dump() for item in body]})


def _legacy_add_parts_batch(gid: str, body: List[CreatePartBody], current_user: dict = Depends(_WRITE)):
    """批量添加零件（用于 Excel 导入）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_bop_pbom_versions WHERE gid = %s", (gid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="PBOM 版本不存在")
            inserted = 0
            for b in body:
                part_gid = str(next_gid())
                cur.execute(_INSERT_PART_SQL, _part_vals(part_gid, gid, b))
                inserted += 1
        conn.commit()
    return {"success": True, "data": {"inserted": inserted}}


@router.patch("/parts/{gid}")
async def update_part(gid: str, body: UpdatePartBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.part.update", {"part_gid": gid, "changes": body.model_dump(exclude_none=True)})


def _legacy_update_part(gid: str, body: UpdatePartBody, current_user: dict = Depends(_WRITE)):
    # workmanship_bop_pbom.name 已重命名为 title，做列名映射
    _COL_REMAP = {'name': 'title'}
    raw = {k: v for k, v in body.model_dump().items() if v is not None}
    updates = {_COL_REMAP.get(k, k): v for k, v in raw.items()}
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_bop_pbom SET {set_clause} WHERE gid = %s",
                list(updates.values()) + [gid]
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="零件不存在")
        conn.commit()
    return {"success": True}


@router.delete("/parts/{gid}")
async def delete_part(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.part.delete", {"part_gid": gid})


def _legacy_delete_part(gid: str, current_user: dict = Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_bop_pbom WHERE gid = %s", (gid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="零件不存在")
        conn.commit()
    return {"success": True}


# ── PBOM 对比（AI 助手用） ─────────────────────────────────────────────────────

_CMP_FIELDS = [
    "name", "quantity", "unit", "material",
    "component_type", "component_version_status", "purchase_status",
    "torque", "torque_importance", "variable_formula",
    "vpps_desc", "parent_vpps", "parent_vpps_name",
    "bom_row", "bom_row_label", "ownership_user", "configuration",
    "parent_bom_row",
]

_FIELD_LABELS = {
    "name": "名称", "quantity": "数量", "unit": "单位", "material": "材料",
    "component_type": "类型", "component_version_status": "版本状态",
    "purchase_status": "采购状态", "torque": "扭矩", "torque_importance": "扭矩重要度",
    "variable_formula": "变量公式", "vpps_desc": "VPPS描述",
    "parent_vpps": "父级VPPS", "parent_vpps_name": "父级名称",
    "bom_row": "BOM行", "bom_row_label": "BOM行标签",
    "ownership_user": "所有权用户", "home": "Home",
    "configuration": "配置", "parent_bom_row": "父级BOM行",
}


def _match_key(p: dict) -> str:
    bom  = (p.get("bom_row") or "").strip()
    cid  = (p.get("component_id") or "").strip()
    vpps = (p.get("vpps") or "").strip()
    pno  = (p.get("part_no") or "").strip()
    if bom and cid: return f"{bom}|{cid}"
    if bom:  return bom
    if vpps: return vpps
    if cid:  return cid
    if pno:  return pno
    return ""


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return str(round(v, 6))
    return str(v).strip()


def _load_parts(cur, snapshot_gid: str) -> list[dict]:
    cols = ["gid", "part_no", "title AS name", "quantity", "unit", "material",
            "vpps", "vpps_desc", "parent_vpps", "parent_vpps_name",
            "bom_row", "bom_row_label", "component_id",
            "component_type", "component_version_status", "purchase_status",
            "torque", "torque_importance", "variable_formula",
            "ownership_user", "home", "configuration", "parent_bom_row", "level"]
    cur.execute(
        f"SELECT {', '.join(cols)} FROM workmanship_bop_pbom WHERE snapshot_gid = %s ORDER BY level, bom_row, part_no",
        (snapshot_gid,),
    )
    return [dict(r) for r in cur.fetchall()]


def _legacy_vpps_check(
    snapshot_gid: str = Query(..., description="PBOM 快照 GID"),
    _u=Depends(_READ),
):
    """
    对指定 PBOM 快照执行 VPPS 核对（四条规则），供 AI 助手调用。
    规则1：主数据核对  规则2：父级一致性  规则3：层级前缀  规则4：紧固件主件一致性
    """
    import re as _re, json as _json

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, version_tag, name FROM workmanship_bop_pbom_versions WHERE gid = %s", (snapshot_gid,))
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, f"PBOM 快照不存在: {snapshot_gid}")
            cur.execute(
                f"SELECT {_PART_COLS} FROM workmanship_bop_pbom WHERE snapshot_gid = %s ORDER BY level, bom_row",
                (snapshot_gid,),
            )
            parts = [dict(r) for r in cur.fetchall()]
            # 不过滤 status：前端 /api/craft_lib/part_names 也不过滤，
            # 且 batch_add_from_pbom 写入的记录 status='有效'（非 'active'），
            # 过滤会导致 Rule 1 大量误报。
            cur.execute(
                "SELECT gid, vpps, vpps_description, vpps_desc_cn, alias "
                "FROM workmanship_tpl_vpps_parts"
            )
            vpps_ref_rows = cur.fetchall()
            # 查询已通过让步的 rule4 行（is_active=TRUE 的 rule4_bulk_ignore 操作）
            try:
                cur.execute(
                    "SELECT pbom_row_gid FROM vpps_operations "
                    "WHERE pbom_version_gid = %s AND operation_type = 'rule4_bulk_ignore' AND is_active = TRUE",
                    (snapshot_gid,),
                )
                ignored_rule4_gids: set = {r["pbom_row_gid"] for r in cur.fetchall()}
            except Exception:
                _log.warning("pbom export: 查询 rule4_bulk_ignore 失败", exc_info=True)
                ignored_rule4_gids = set()

    # ── 主数据索引 ─────────────────────────────────────────────────
    ref_map: dict = {}
    alias_map: dict = {}
    for r in vpps_ref_rows:
        v = (r["vpps"] or "").strip()
        if v:
            ref_map[v] = r
        raw_alias = r["alias"] or []
        if isinstance(raw_alias, str):
            try: raw_alias = _json.loads(raw_alias)
            except: raw_alias = []
        for a in raw_alias:
            a = (a or "").strip()
            if a:
                alias_map[a] = {"vpps_part_gid": r["gid"], "canonical_vpps": v}

    # ── 描述规范化（去 '-' 前缀，只保留中文字符）─────────────────
    def _norm_desc(s: str) -> str:
        s = (s or "").strip()
        d = s.find("-")
        if d != -1:
            s = s[d + 1:]
        return _re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbf]", "", s)

    errors: list = []
    alias_matches: list = []
    by_bom_row = {(p.get("bom_row") or "").strip(): p
                  for p in parts if (p.get("bom_row") or "").strip()}

    # ── 规则 1 + 3（仅 level=3 零件，与前端一致）───────────────────
    for idx, p in enumerate(parts):
        # L1/L2 装配体跳过（与前端一致：只检查 level==3 零件）
        lv = p.get("level")
        if lv is not None and lv != 3:
            continue
        vpps        = (p.get("vpps")        or "").strip()
        desc        = (p.get("vpps_desc")   or "").strip()
        parent_vpps = (p.get("parent_vpps") or "").strip()
        if not vpps:
            continue
        ref = ref_map.get(vpps)
        if not ref:
            errors.append({"rule": 1, "vpps": vpps, "row": idx + 1,
                           "msg": f'VPPS "{vpps}" 在主数据中不存在'})
        elif desc:
            ref_en = (ref["vpps_description"] or "").strip()
            ref_cn = (ref["vpps_desc_cn"]     or "").strip()
            # 规范化比较：去掉 '-' 前缀，只比汉字部分（与前端 _normVppsDesc 一致）
            desc_n  = _norm_desc(desc)
            ref_en_n = _norm_desc(ref_en)
            ref_cn_n = _norm_desc(ref_cn)
            matched = (desc_n and (desc_n == ref_en_n or desc_n == ref_cn_n)) \
                      or desc == ref_en or desc == ref_cn
            if not matched:
                alias_hit = alias_map.get(desc)
                if alias_hit and alias_hit["canonical_vpps"] == vpps:
                    alias_matches.append({"vpps": vpps, "row": idx + 1, "desc": desc})
                else:
                    errors.append({"rule": 1, "vpps": vpps, "row": idx + 1,
                                   "msg": f'描述不一致: "{desc}" ≠ 主数据"{ref_cn or ref_en}"'})
        if parent_vpps:
            # 规则3：使用 prefix+'.' 避免 "ABC.1" 误匹配 "ABC.10"（与前端一致）
            prefix = parent_vpps.rstrip(".")
            if not (vpps.startswith(prefix + ".") or vpps == prefix):
                errors.append({"rule": 3, "vpps": vpps, "row": idx + 1,
                               "msg": f'层级不匹配: "{vpps}" 不以父级 "{parent_vpps}" 开头'})

    # ── 规则 2（仅 level=3，与前端一致）────────────────────────────
    by_gid = {p["gid"]: p for p in parts if p.get("gid")}
    for idx, p in enumerate(parts):
        lv = p.get("level")
        if lv is not None and lv != 3:
            continue
        pv_field = (p.get("parent_vpps")    or "").strip()
        pbr      = (p.get("parent_bom_row") or "").strip()
        pgid     = (p.get("parent_gid")     or "").strip()
        if not pv_field:
            continue
        parent_part = by_bom_row.get(pbr) or (by_gid.get(pgid) if pgid else None)
        if parent_part is None:
            continue
        actual = (parent_part.get("vpps") or "").strip()
        if actual and actual != pv_field:
            label = (p.get("vpps") or p.get("part_no") or "-").strip()
            errors.append({"rule": 2, "vpps": label, "row": idx + 1,
                           "msg": f'父级VPPS字段"{pv_field}" ≠ 父级零件实际VPPS"{actual}"'})

    # ── 规则 4：紧固件主件一致性 ─────────────────────────────────────
    FASTENER_TYPES = {"标准件", "非标件"}
    # 装置是装配体，AABB 覆盖全部子件必然误报，与前端一致只用零部件
    STRUCT_TYPES   = {"零部件"}

    def _parse_mat(s):
        if not s: return None
        try:
            v = list(map(float, s.split()))
            return v if len(v) == 16 else None
        except: return None

    def _parse_bbox(s):
        if not s: return None
        try:
            v = list(map(float, s.split(",")))
            return v if len(v) == 6 else None
        except: return None

    def _world_bbox(mat, bbox):
        xmin,ymin,zmin,xmax,ymax,zmax = bbox
        corners = [(xmin,ymin,zmin),(xmax,ymin,zmin),(xmin,ymax,zmin),(xmax,ymax,zmin),
                   (xmin,ymin,zmax),(xmax,ymin,zmax),(xmin,ymax,zmax),(xmax,ymax,zmax)]
        wxs,wys,wzs = [],[],[]
        for cx,cy,cz in corners:
            wxs.append(cx*mat[0]+cy*mat[4]+cz*mat[8] +mat[12])
            wys.append(cx*mat[1]+cy*mat[5]+cz*mat[9] +mat[13])
            wzs.append(cx*mat[2]+cy*mat[6]+cz*mat[10]+mat[14])
        return (min(wxs),min(wys),min(wzs)),(max(wxs),max(wys),max(wzs))

    def _overlap(mn1,mx1,mn2,mx2):
        dx=max(0.0,min(mx1[0],mx2[0])-max(mn1[0],mn2[0]))
        dy=max(0.0,min(mx1[1],mx2[1])-max(mn1[1],mn2[1]))
        dz=max(0.0,min(mx1[2],mx2[2])-max(mn1[2],mn2[2]))
        return dx*dy*dz

    def _extract_ab(vpps_desc):
        if not vpps_desc: return None, None, None
        s = _re.sub(r'\(.*?\)', '', vpps_desc).strip()
        dash = s.find('-')
        if dash == -1: return None, None, None
        after = s[dash+1:].strip()
        for sep in ['到', '与']:
            if sep in after:
                a, b = after.split(sep, 1)
                return a.strip(), b.strip(), sep
        return after.strip(), None, None

    def _lr(name): return '左' if '左' in name else ('右' if '右' in name else '')

    def _sim(query, part_name, thr=0.60):
        if not query or not part_name: return 0
        if query == part_name: return len(query)*10
        best = 0
        for i in range(len(query)):
            for j in range(i+2, len(query)+1):
                sub = query[i:j]
                if sub in part_name and len(sub) > best: best = len(sub)
        return best if best > 0 and best/len(part_name) >= thr else 0

    def _match(a_str, candidates):
        if not a_str or not candidates: return None
        elig = [c for c in candidates
                if not ('支架' not in a_str and '支架' in (c.get('name') or ''))]
        best, best_sc = None, 0
        for c in elig:
            sc = _sim(a_str, c.get('name') or '')
            if sc > best_sc: best_sc = sc; best = c
        return best

    def _match_ab(a_str, b_str, sep, candidates):
        ma = _match(a_str, candidates)
        if sep != '与' or not b_str: return ma
        mb = _match(b_str, candidates)
        if not ma: return mb
        if not mb: return ma
        return ma if _sim(a_str, ma.get('name') or '') >= _sim(b_str, mb.get('name') or '') else mb

    parent_to_struct: dict = {}
    for p in parts:
        if (p.get("component_type") or "").strip() not in STRUCT_TYPES: continue
        pbr = (p.get("parent_bom_row") or "").strip()
        if pbr:
            parent_to_struct.setdefault(pbr, []).append(p)

    rule4_errors: list = []
    rule4_ignored: list = []    # 已让步（跳过）的紧固件行，用于统计
    for idx, p in enumerate(parts):
        if (p.get("component_type") or "").strip() not in FASTENER_TYPES: continue
        # 已通过让步操作忽略的行：跳过 rule4 检查，记录到 rule4_ignored
        if p.get("gid") and p["gid"] in ignored_rule4_gids:
            rule4_ignored.append({"vpps": (p.get("vpps") or "").strip(), "row": idx + 1})
            continue
        pbr      = (p.get("parent_bom_row") or "").strip()
        siblings = list(parent_to_struct.get(pbr, [])) if pbr else []
        if not siblings: continue
        a_str, b_str, ab_sep = _extract_ab(p.get("vpps_desc") or "")
        # 几何池：用紧固件物理左右过滤（名称可靠，物理位置不会错）
        geo_siblings = siblings
        f_lr = _lr(p.get("name") or "")
        if f_lr and len(siblings) > 1:
            same = [s for s in siblings if _lr(s.get("name") or "") == f_lr]
            if same: geo_siblings = same
        # VPPS 描述池：不做左右预过滤，a_str 本身含左右信息，相似度会自然倾向正确侧
        # 这样才能检测出"紧固件名称说右、但 VPPS 描述指向左侧主件"的矛盾
        vpps_siblings = siblings
        geo_main = None
        f_mat  = _parse_mat(p.get("abs_matrix") or "")
        f_bbox = _parse_bbox(p.get("local_bbox") or "")
        if f_mat and f_bbox:
            f_wmin, f_wmax = _world_bbox(f_mat, f_bbox)
            best_vol = 0.0
            for s in geo_siblings:
                s_mat  = _parse_mat(s.get("abs_matrix") or "")
                s_bbox = _parse_bbox(s.get("local_bbox") or "")
                if not s_mat or not s_bbox: continue
                s_wmin, s_wmax = _world_bbox(s_mat, s_bbox)
                vol = _overlap(f_wmin, f_wmax, s_wmin, s_wmax)
                if vol > best_vol: best_vol = vol; geo_main = s
        vpps_main  = _match_ab(a_str, b_str, ab_sep, vpps_siblings)
        vpps_label = (p.get("vpps") or p.get("name") or "").strip()
        if geo_main and vpps_main:
            geo_id  = (geo_main.get("catia_file_name")  or geo_main.get("name")  or "").strip()
            vpps_id = (vpps_main.get("catia_file_name") or vpps_main.get("name") or "").strip()
            if geo_id and vpps_id and geo_id != vpps_id:
                ref_str = (f'VPPS描述AB="{a_str}与{b_str}"→最佳匹配"{vpps_main.get("name")}"'
                           if ab_sep == "与" else
                           f'VPPS描述A="{a_str}"→"{vpps_main.get("name")}"')
                rule4_errors.append({"rule": 4, "vpps": vpps_label, "row": idx + 1,
                    "gid": p.get("gid", ""), "vpps_desc": p.get("vpps_desc", ""),
                    "msg": f'主件不一致: 几何主件="{geo_main.get("name")}" vs {ref_str}'})
        elif not geo_main and a_str:
            cons = (p.get("main_part_consistency") or "").strip()
            if "⚠" in cons:
                rule4_errors.append({"rule": 4, "vpps": vpps_label, "row": idx + 1,
                    "gid": p.get("gid", ""), "vpps_desc": p.get("vpps_desc", ""),
                    "msg": f"主件不一致(无几何): {cons}"})

    # ── 汇总返回 ────────────────────────────────────────────────────
    all_errors = errors + rule4_errors
    r1 = [e for e in errors    if e["rule"] == 1]
    r2 = [e for e in errors    if e["rule"] == 2]
    r3 = [e for e in errors    if e["rule"] == 3]
    parts_with_vpps = sum(1 for p in parts if (p.get("vpps") or "").strip())
    return {
        "snapshot": {
            "gid": snapshot_gid,
            "version_tag": ver["version_tag"],
            "name": ver["name"] or "",
        },
        "summary": {
            "total_parts":       len(parts),
            "parts_with_vpps":   parts_with_vpps,
            "rule1_errors":      len(r1),
            "rule2_errors":      len(r2),
            "rule3_errors":      len(r3),
            "rule4_errors":      len(rule4_errors),
            "rule4_ignored":     len(rule4_ignored),  # 已让步的紧固件行数
            "alias_matches":     len(alias_matches),
            "ok":                len(all_errors) == 0,
        },
        "errors": {
            "rule1": r1,
            "rule2": r2,
            "rule3": r3,
            "rule4": rule4_errors,
        },
        "alias_matches":  alias_matches,
        "rule4_ignored":  rule4_ignored,  # 让步明细，供 AI 说明
    }


@router.get("/vpps_check")
async def vpps_check(
    snapshot_gid: str = Query(..., description="PBOM 快照 GID"),
    request: Request = None,
    _u=Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    """Run deterministic VPPS checks through the governed read Capability."""
    request_id = request.headers.get("X-Request-ID") or f"craft_ebom_vpps_{uuid4().hex}"
    result = await invoke_compatibility(
        gateway,
        build_web_compatibility_envelope(
            gateway,
            capability_id="craft.ebom.vpps_check.read",
            payload={"operation": "check", "snapshot_gid": snapshot_gid},
            current_user=_u,
            principal=principal,
            request_id=request_id,
            trace_id=request.headers.get("X-Trace-ID") or request_id,
        ),
    )
    if not result.ok:
        error = result.error
        status = {"resource_not_found": 404, "forbidden": 403, "invalid_input": 400}.get(error.code if error else "", 422)
        raise HTTPException(status_code=status, detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


def _legacy_diff_snapshots(
    base_gid:   str = Query(..., description="基准 PBOM 快照 GID"),
    target_gid: str = Query(..., description="目标 PBOM 快照 GID"),
    _u=Depends(_READ),
):
    """
    对比两个 PBOM 快照，返回新增 / 删除 / 变更 / 统计信息。
    供 AI 助手调用，结果以结构化 JSON 返回，已去掉无变化行。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 检查快照存在
            cur.execute("SELECT gid, version_tag, name FROM workmanship_bop_pbom_versions WHERE gid = %s", (base_gid,))
            base_ver = cur.fetchone()
            if not base_ver:
                raise HTTPException(404, f"base 快照不存在: {base_gid}")
            cur.execute("SELECT gid, version_tag, name FROM workmanship_bop_pbom_versions WHERE gid = %s", (target_gid,))
            target_ver = cur.fetchone()
            if not target_ver:
                raise HTTPException(404, f"target 快照不存在: {target_gid}")

            base_parts   = _load_parts(cur, base_gid)
            target_parts = _load_parts(cur, target_gid)

    # 构建 matchKey → part 映射（重复 key 加 #N 后缀）
    def _build_map(parts):
        cnt: dict = {}
        m: dict = {}
        for p in parts:
            k = _match_key(p)
            if not k:
                continue
            n = cnt.get(k, 0)
            cnt[k] = n + 1
            mk = f"{k}#{n}" if n > 0 else k
            p["_mk"] = mk
            m[mk] = p
        return m

    base_map   = _build_map(base_parts)
    target_map = _build_map(target_parts)

    added, deleted, modified, same_count = [], [], [], 0

    for mk, tp in target_map.items():
        if mk not in base_map:
            added.append({"match_key": mk, "part_no": tp.get("part_no", ""), "name": tp.get("name", "")})

    for mk, bp in base_map.items():
        if mk not in target_map:
            deleted.append({"match_key": mk, "part_no": bp.get("part_no", ""), "name": bp.get("name", "")})

    for mk, tp in target_map.items():
        bp = base_map.get(mk)
        if bp is None:
            continue
        changes = []
        for f in _CMP_FIELDS:
            bv, tv = _norm(bp.get(f)), _norm(tp.get(f))
            if bv != tv:
                changes.append({
                    "field": f,
                    "label": _FIELD_LABELS.get(f, f),
                    "from":  bv or "-",
                    "to":    tv or "-",
                })
        if changes:
            modified.append({
                "match_key":     mk,
                "part_no":       tp.get("part_no", ""),
                "name":          tp.get("name", ""),
                "changed_fields": changes,
            })
        else:
            same_count += 1

    return {
        "base":   {"gid": base_gid,   "version_tag": base_ver["version_tag"],   "name": base_ver["name"] or ""},
        "target": {"gid": target_gid, "version_tag": target_ver["version_tag"], "name": target_ver["name"] or ""},
        "summary": {
            "total_base":   len(base_parts),
            "total_target": len(target_parts),
            "added":        len(added),
            "deleted":      len(deleted),
            "modified":     len(modified),
            "same":         same_count,
        },
        "added":    added,
        "deleted":  deleted,
        "modified": modified,
    }


@router.get("/diff")
async def diff_snapshots(
    base_gid: str = Query(..., description="基准 PBOM 快照 GID"),
    target_gid: str = Query(..., description="目标 PBOM 快照 GID"),
    request: Request = None,
    _u=Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    """Compare two PBOM snapshots through the bounded legacy-read Capability."""
    request_id = request.headers.get("X-Request-ID") or f"craft_ebom_diff_{uuid4().hex}"
    result = await invoke_compatibility(
        gateway,
        build_web_compatibility_envelope(
            gateway,
            capability_id="craft.ebom.legacy_read",
            payload={
                "operation": "diff",
                "base_gid": base_gid,
                "target_gid": target_gid,
            },
            current_user=_u,
            principal=principal,
            request_id=request_id,
            trace_id=request.headers.get("X-Trace-ID") or request_id,
        ),
    )
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(
            status_code={
                "resource_not_found": 404,
                "permission_denied": 403,
                "invalid_input": 400,
            }.get(code, 422),
            detail=result.error.model_dump(mode="json") if result.error else None,
        )
    return result.data["data"]
