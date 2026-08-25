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




class VppsStatsBody(BaseModel):
    nok:     int = 0
    ignored: int = 0
    total:   int = 0


@router.patch("/snapshots/{gid}/vpps-stats", status_code=200)
async def patch_vpps_stats(gid: str, body: VppsStatsBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.snapshot.vpps_stats.update", {"snapshot_gid": gid, **body.model_dump()})



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




@router.post("/snapshots/{gid}/parts/batch", status_code=201)
async def add_parts_batch(gid: str, body: List[CreatePartBody], request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.part.bulk_create", {"snapshot_gid": gid, "parts": [item.model_dump() for item in body]})




@router.patch("/parts/{gid}")
async def update_part(gid: str, body: UpdatePartBody, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.part.update", {"part_gid": gid, "changes": body.model_dump(exclude_none=True)})




@router.delete("/parts/{gid}")
async def delete_part(gid: str, request: Request, current_user: dict = Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_ebom_atomic(request, current_user, principal, gateway, "craft.ebom.part.delete", {"part_gid": gid})




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
