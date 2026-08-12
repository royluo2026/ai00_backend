"""
backend/routers/_bop/versions.py
─────────────────────────────────
BOP 版本 CRUD + 生命周期 + 画布全量数据 + V1 废弃端点。
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...data.connection import get_conn
from backend.platform_sdk.ids import next_gid
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from ..factory import _invoke as _invoke_factory

from ._constants import _WRITE, _READ, _VER_COLS, _VER_KEYS, _SEC_COLS, _SEC_KEYS, _STA_COLS, _STA_KEYS
from ._helpers import _row, _rows, _not_found, _snapshot_links, _clear_snapshots, _copy_entries_and_links

router = APIRouter(prefix="/api/bop", tags=["bop"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class CreateBopVersionBody(BaseModel):
    version_tag: str
    bop_name: str = ''
    version_family_gid: Optional[str] = None
    project_gid: Optional[str] = None
    factory_gid: Optional[str] = None
    vehicle_model_gid: Optional[str] = None
    maturity: str = 'concept'
    takt_time: float = 60
    version_type: str = 'working'
    pbom_version_gid: Optional[str] = None
    owner_gid: Optional[str] = None
    data_stage: Optional[str] = None


class UpdateBopVersionBody(BaseModel):
    version_tag:        Optional[str]   = None
    bop_name:           Optional[str]   = None
    maturity:           Optional[str]   = None
    takt_time:          Optional[float] = None
    status:             Optional[str]   = None
    factory_gid:        Optional[str]   = None
    vehicle_model_gid:  Optional[str]   = None
    visibility:         Optional[str]   = None
    shared_team_gid:    Optional[str]   = None
    shared_project_gid: Optional[str]   = None
    data_stage:         Optional[str]   = None
    pbom_version_gid:   Optional[str]   = None


class LayoutConfigBody(BaseModel):
    config: dict


class FreezeSnapshotBody(BaseModel):
    target_data_stage: Optional[str] = None  # 冻结后活动版本推进到的阶段；None/空=同阶段（仅升版本号）
    change_note:       Optional[str] = None
    promote_to_m:      bool = False          # 是否直接发布为 M
    bump_version_tag:  bool = True           # 活动版本 version_tag 自动递增（V1 → V2）
    same_stage:        bool = False          # True = 仅升版本号，data_stage 保持不变


# V1 废弃 Pydantic 模型
class CreatePostBody(BaseModel):
    """V1 已废弃"""
    station_gid: str = ""
    post_code: str = ""
    post_name: str = ""
    head_count: int = 1
    sort_order: int = 0


class UpdatePostBody(BaseModel):
    """V1 已废弃"""
    post_code: Optional[str] = None
    post_name: Optional[str] = None
    head_count: Optional[int] = None
    sort_order: Optional[int] = None
    station_gid: Optional[str] = None


class CreateOperationBody(BaseModel):
    """V1 已废弃"""
    op_code: str = ""
    op_name: str = ""
    seq_no: int = 0
    standard_time: float = 0
    std_op_gid: Optional[str] = None


class UpdateOperationBody(BaseModel):
    """V1 已废弃"""
    op_code: Optional[str] = None
    op_name: Optional[str] = None
    seq_no: Optional[int] = None
    standard_time: Optional[float] = None
    std_op_gid: Optional[str] = None
    post_gid: Optional[str] = None
    parts: Optional[list] = None


class CreateStepBody(BaseModel):
    """V1 已废弃"""
    step_code: str = ""
    step_name: str = ""
    seq_no: int = 0
    standard_time: float = 0
    notes: str = ""


class UpdateStepBody(BaseModel):
    """V1 已废弃"""
    step_code: Optional[str] = None
    step_name: Optional[str] = None
    seq_no: Optional[int] = None
    standard_time: Optional[float] = None
    notes: Optional[str] = None


class CreateResourceBody(BaseModel):
    """V1 已废弃"""
    resource_type: str = "tool"
    spec_name: str = ""
    spec_params: dict = {}
    qty: float = 1


class ResetFieldsBody(BaseModel):
    """V1 已废弃"""
    fields: list = []


# ══════════════════════════════════════════════════════════════
# BOP 版本 CRUD
# ══════════════════════════════════════════════════════════════

@router.get("/versions")
def list_versions(
    project_gid: Optional[str] = None,
    factory_gid: Optional[str] = None,
    include_archived: bool = False,
    _u=Depends(_READ),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            where = ["is_deleted = FALSE"]
            params = []
            if not include_archived:
                where.append("archived_at IS NULL")
            if project_gid:
                where.append("project_gid=%s"); params.append(project_gid)
            if factory_gid:
                where.append("factory_gid=%s"); params.append(factory_gid)
            w = "WHERE " + " AND ".join(where)
            cur.execute(
                f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions {w} "
                f"ORDER BY version_family_gid , created_at",
                params
            )
            return {"data": _rows(cur, _VER_KEYS)}


@router.post("/versions", status_code=201)
def create_version(body: CreateBopVersionBody, _u=Depends(_WRITE)):
    gid = str(next_gid())
    family_gid = body.version_family_gid or gid
    # 净化 bop_name：强制去掉 "  ·  <data_stage>" 后缀，版本族名只保留项目名
    import re as _re
    clean_bop_name = _re.sub(r'\s*[·＇・]\s*\S+$', '', (body.bop_name or '')).strip()
    if not clean_bop_name:
        clean_bop_name = (body.bop_name or '').strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if body.pbom_version_gid:
                cur.execute(
                    "SELECT status FROM workmanship_bop_pbom_versions WHERE gid=%s",
                    (body.pbom_version_gid,)
                )
                pbom_ver = cur.fetchone()
                if not pbom_ver or pbom_ver['status'] != 'ready':
                    raise HTTPException(400, "PBOM 版本尚未就绪（status != 'ready'），无法关联该 PBOM 版本")
            cur.execute(
                f"INSERT INTO workmanship_bop_bop_versions "
                f"(gid,version_tag,bop_name,version_family_gid,"
                f"project_gid,factory_gid,vehicle_model_gid,maturity,takt_time,"
                f"status,meta,lifecycle_phase,lifecycle_state,visibility,version_type,pbom_version_gid,owner_gid,data_stage) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.version_tag, clean_bop_name, family_gid,
                 body.project_gid, body.factory_gid,
                 body.vehicle_model_gid, body.maturity, body.takt_time,
                 'active', json.dumps({}), 'init', json.dumps({}), 'team', body.version_type,
                 body.pbom_version_gid, body.owner_gid, body.data_stage)
            )
            conn.commit()
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            return {"data": _row(cur, _VER_KEYS)}


@router.get("/versions/{gid}")
def get_version(gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = _row(cur, _VER_KEYS)
            if not row: _not_found(gid)
            return {"data": row}


@router.patch("/versions/{gid}")
def update_version(gid: str, body: UpdateBopVersionBody, _u=Depends(_WRITE)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "无更新字段")
    updates['updated_at'] = 'NOW()'
    set_parts = []
    vals = []
    for k, v in updates.items():
        if v == 'NOW()':
            set_parts.append(f"{k}=NOW()")
        else:
            set_parts.append(f"{k}=%s")
            vals.append(v)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_bop_bop_versions SET {', '.join(set_parts)} WHERE gid=%s",
                vals + [gid]
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = _row(cur, _VER_KEYS)
            if not row: _not_found(gid)
            conn.commit()
            return {"data": row}


@router.get("/versions/{gid}/layout-config")
def get_layout_config(gid: str, _u=Depends(_READ)):
    """读取 BOP 版本的共享布局视图配置"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT JSON_EXTRACT(meta,'$.view_config') AS cfg FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "版本不存在")
            return {"config": row["cfg"]}


@router.put("/versions/{gid}/layout-config", status_code=200)
def put_layout_config(gid: str, body: LayoutConfigBody, _u=Depends(_WRITE)):
    """写入 BOP 版本的共享布局视图配置"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_bop_bop_versions "
                "SET meta = JSON_SET(IFNULL(meta,'{}'), '$.view_config', CAST(%s AS JSON)), "
                "    updated_at = NOW() "
                "WHERE gid=%s",
                (json.dumps(body.config), gid)
            )
    return {"success": True}


@router.get("/versions/{version_gid}/bop-tree")
def get_bop_tree(version_gid: str, _u=Depends(_READ)):
    """返回 BOP 版本完整层级树 JSON"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gid, parent_gid, node_type, sort_order, title
                FROM workmanship_bop_bop_entries
                WHERE version_gid = %s AND is_deleted = FALSE
                ORDER BY sort_order
            """, (version_gid,))
            rows = [dict(r) for r in cur.fetchall()]

    entry_map = {r['gid']: r for r in rows}
    children  = {}
    roots     = []
    for r in rows:
        p = r['parent_gid']
        if p and p in entry_map:
            children.setdefault(p, []).append(r['gid'])
        else:
            roots.append(r['gid'])

    def build_node(gid):
        e = entry_map[gid]
        kids = sorted(children.get(gid, []), key=lambda g: entry_map[g]['sort_order'] or 0)
        return {
            "name":      e['title'] or e['node_type'],
            "path":      gid,
            "gid":       gid,
            "node_type": e['node_type'],
            "sort_order": e['sort_order'],
            "is_leaf":   len(kids) == 0,
            "children":  [build_node(k) for k in kids],
        }

    return {"tree": [build_node(r) for r in roots]}


@router.get("/versions/{version_gid}/station-part-map")
def get_station_part_map(version_gid: str, _u=Depends(_READ)):
    """按工位分组返回零件列表"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gid, parent_gid, node_type, sort_order, title
                FROM workmanship_bop_bop_entries
                WHERE version_gid = %s AND is_deleted = FALSE
                ORDER BY sort_order
            """, (version_gid,))
            entries = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT l.entry_gid,
                       p.gid AS part_gid, p.part_no, p.title AS part_name,
                       p.bom_row, p.vpps
                FROM workmanship_bop_bop_entry_links l
                JOIN workmanship_bop_pbom p ON p.gid = l.entity_gid
                JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid
                WHERE e.version_gid = %s AND l.link_type = 'pbom_part'
            """, (version_gid,))
            links = [dict(r) for r in cur.fetchall()]

    entry_map    = {e['gid']: e for e in entries}
    children_map = {}
    for e in entries:
        if e['parent_gid']:
            children_map.setdefault(e['parent_gid'], []).append(e['gid'])

    entry_parts = {}
    for lk in links:
        entry_parts.setdefault(lk['entry_gid'], []).append(lk)

    def get_all_descendants(gid):
        result = []
        for child in children_map.get(gid, []):
            result.append(child)
            result.extend(get_all_descendants(child))
        return result

    stations = []
    for e in entries:
        if e['node_type'] != 'station_process':
            continue
        desc_gids = get_all_descendants(e['gid'])
        parts, seen = [], set()
        for d_gid in [e['gid']] + desc_gids:
            for p in entry_parts.get(d_gid, []):
                if p['part_gid'] not in seen:
                    seen.add(p['part_gid'])
                    parts.append(dict(p))
        stations.append({
            'gid':        e['gid'],
            'name':       e['title'],
            'sort_order': e['sort_order'] or 0,
            'parts':      parts,
        })

    stations.sort(key=lambda s: s['sort_order'])
    return {"stations": stations}


# ── 版本生命周期 ──────────────────────────────────────────────────────────────

@router.post("/versions/{gid}/freeze", status_code=200)
def freeze_version(gid: str, _u=Depends(_WRITE)):
    """冻结版本：active → baseline，执行快照"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, "版本不存在")
            if ver['status'] != 'active':
                raise HTTPException(400, f"只有 active 状态可冻结，当前: {ver['status']}")
            _snapshot_links(cur, gid)
            cur.execute(
                f"UPDATE workmanship_bop_bop_versions SET status='baseline', frozen_at=NOW(), updated_at=NOW() "
                f"WHERE gid=%s",
                (gid,)
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = _row(cur, _VER_KEYS)
            conn.commit()
            return {"data": row}


@router.post("/versions/{gid}/unfreeze", status_code=200)
def unfreeze_version(gid: str, _u=Depends(_WRITE)):
    """解冻版本：baseline → active，清除快照"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, "版本不存在")
            if ver['status'] != 'baseline':
                raise HTTPException(400, f"只有 baseline 状态可解冻，当前: {ver['status']}")
            _clear_snapshots(cur, gid)
            cur.execute(
                f"UPDATE workmanship_bop_bop_versions SET status='active', frozen_at=NULL, updated_at=NOW() "
                f"WHERE gid=%s",
                (gid,)
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = _row(cur, _VER_KEYS)
            conn.commit()
            return {"data": row}


@router.post("/versions/{gid}/publish", status_code=200)
def publish_version(gid: str, _u=Depends(_WRITE)):
    """发布版本：baseline → M"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, "版本不存在")
            if ver['status'] != 'baseline':
                raise HTTPException(400, f"只有 baseline 状态可发布，当前: {ver['status']}")
            cur.execute(
                f"UPDATE workmanship_bop_bop_versions SET status='M', published_at=NOW(), updated_at=NOW() "
                f"WHERE gid=%s",
                (gid,)
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = _row(cur, _VER_KEYS)
            conn.commit()
            return {"data": row}


@router.post("/versions/{gid}/freeze-snapshot", status_code=201)
def freeze_snapshot(gid: str, body: FreezeSnapshotBody, _u=Depends(_WRITE)):
    """
    新版冻结/升版：活动版本原地保持 active，fork 出副本变 baseline/M。
    - 副本携带：当前所有条目/链接快照 + lifecycle_state 快照，保留旧 data_stage
    - 活动版本：
        · same_stage=True 或 target_data_stage 为空 → data_stage 不变（仅 version_tag 自增）
        · 否则 → data_stage 推进，lifecycle_state 完善指标缓存清空
    """
    from datetime import datetime, timezone
    import re as _re
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 验证源版本存在且为 active
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            src = cur.fetchone()
            if not src:
                raise HTTPException(404, f"版本 {gid} 不存在")
            src = dict(src)
            if src.get('status') != 'active':
                raise HTTPException(400, f"只有 active 版本才能升版（当前状态：{src.get('status')}）")

            # 判断升版模式：同阶段仅版本号 / 推进到新 data_stage
            same_stage = bool(body.same_stage) or not body.target_data_stage
            current_stage = src.get('data_stage') or ''
            new_stage = current_stage if same_stage else body.target_data_stage

            snap_gid   = str(next_gid())
            snap_status = 'M' if body.promote_to_m else 'baseline'
            now_iso    = datetime.now(timezone.utc).isoformat()

            # 计算 change_note 默认值
            if body.change_note:
                change_note = body.change_note
            elif same_stage:
                change_note = f'升版（同阶段 {current_stage}）'
            else:
                change_note = f'升版 → {new_stage}'

            # 2. 创建快照副本（继承源版本字段，data_stage 保留当前阶段，version_tag 保留旧值）
            cur.execute(f"""
                INSERT INTO workmanship_bop_bop_versions
                  (gid, version_tag, bop_name, version_family_gid,
                   project_gid, factory_gid, vehicle_model_gid,
                   maturity, takt_time, version_type, pbom_version_gid,
                   owner_gid, data_stage, parent_version_gid,
                   change_note, status, frozen_at, published_at,
                   lifecycle_phase, lifecycle_state, meta, visibility,
                   created_at, updated_at)
                SELECT
                  %s, version_tag, bop_name, version_family_gid,
                  project_gid, factory_gid, vehicle_model_gid,
                  maturity, takt_time, version_type, pbom_version_gid,
                  owner_gid, data_stage, %s,
                  %s, %s, NOW(), %s,
                  lifecycle_phase, lifecycle_state, meta, visibility,
                  NOW(), NOW()
                FROM workmanship_bop_bop_versions WHERE gid=%s
            """, (
                snap_gid, gid,
                change_note,
                snap_status,
                now_iso if body.promote_to_m else None,
                gid
            ))
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (snap_gid,))
            snap_ver = _row(cur, _VER_KEYS)

            # 3. 复制条目和链接到副本（source_entry_gid 记录溯源）
            _copy_entries_and_links(cur, gid, snap_gid)

            # 4. 原版本：推进或保持 data_stage，version_tag 自增，清空完善指标缓存（仅推进时）
            # version_tag 自增：V1 → V2、V02 → V03、纯数字 → +1
            old_tag = src.get('version_tag') or 'V1'
            m = _re.match(r'^([A-Za-z]*)(\d+)$', old_tag)
            if m:
                prefix, num = m.group(1), m.group(2)
                width = len(num)
                new_tag = f"{prefix}{str(int(num) + 1).zfill(width)}"
            else:
                new_tag = f"{old_tag}+1"

            cur.execute("SELECT lifecycle_state FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row2 = cur.fetchone()
            ls = dict(row2)['lifecycle_state'] or {}
            if isinstance(ls, str):
                try:
                    ls = json.loads(ls) if ls else {}
                except Exception:
                    ls = {}
            if not same_stage:
                # 推进 data_stage 时，清空 refine_stats 缓存（保留 init checklist）
                ls.pop('refine_stats', None)

            cur.execute("""
                UPDATE workmanship_bop_bop_versions
                SET data_stage=%s, version_tag=%s, lifecycle_state=%s, updated_at=NOW()
                WHERE gid=%s
            """, (new_stage, new_tag, json.dumps(ls), gid))

            # 5. 同步族群表 updated_at（如果族群表已建立）
            try:
                cur.execute("""
                    UPDATE workmanship_bop_bop_version_families
                    SET updated_at=NOW()
                    WHERE active_version_gid=%s
                """, (gid,))
            except Exception:
                pass  # 表未建时静默忽略

            conn.commit()
            return {
                "snapshot_gid":    snap_gid,
                "snapshot_status": snap_status,
                "new_data_stage":  new_stage,
                "new_version_tag": new_tag,
                "same_stage":      same_stage,
                "snapshot":        snap_ver,
            }


# 别名路由：语义更直观的"升版"入口（行为同 freeze-snapshot）
@router.post("/versions/{gid}/promote", status_code=201)
def promote_version(gid: str, body: FreezeSnapshotBody, _u=Depends(_WRITE)):
    """升版别名 — 等同于 freeze-snapshot，便于前端语义化调用。"""
    return freeze_snapshot(gid, body, _u)


@router.post("/version-families/{family_gid}/archive", status_code=200)
def archive_family(family_gid: str, _u=Depends(_WRITE)):
    """归档版本族"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET status='archived', archived_at=NOW(), updated_at=NOW() "
                "WHERE version_family_gid=%s AND status IN ('baseline','M') AND is_deleted = FALSE",
                (family_gid,)
            )
            count = cur.rowcount
            conn.commit()
            return {"data": {"archived_count": count}}


@router.delete("/version-families/{family_gid}/archive", status_code=200)
def unarchive_family(family_gid: str, _u=Depends(_WRITE)):
    """解除版本族归档"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_bop_bop_versions "
                "SET status = CASE "
                "    WHEN published_at IS NOT NULL THEN 'M' "
                "    ELSE 'baseline' "
                "  END, "
                "  archived_at = NULL, updated_at = NOW() "
                "WHERE version_family_gid=%s AND status='archived' AND is_deleted = FALSE",
                (family_gid,)
            )
            count = cur.rowcount
            conn.commit()
            return {"data": {"unarchived_count": count}}


# ── 画布全量数据 ──────────────────────────────────────────────────────────────

@router.get("/versions/{gid}/canvas")
async def get_canvas(gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            bop = _row(cur, _VER_KEYS)
            if not bop: _not_found(gid)

            factory_gid = bop.get('factory_gid')
            if not factory_gid:
                return {"data": {"bop": bop, "factory": None}}

            cur.execute(
                "SELECT gid, version_gid, parent_gid, node_type, sort_order, level, "
                "ai00_level, title, vpps, owner_gid, created_at, updated_at "
                "FROM workmanship_bop_bop_entries WHERE version_gid=%s AND is_deleted = FALSE "
                "ORDER BY sort_order",
                (gid,)
            )
            bop_entries_list = [dict(r) for r in cur.fetchall()]

    factory = await _invoke_factory(request, _u, principal, gateway, "factory.structure.get", {"gid": factory_gid})
    return {"data": {"bop": bop, "factory": factory}}


# ══════════════════════════════════════════════════════════════
# V1 废弃端点（岗位 / 工序 / 工步 / 工序资源 / Drift）
# ══════════════════════════════════════════════════════════════

@router.post("/versions/{bop_gid}/posts", status_code=410)
def create_post(bop_gid: str, body: CreatePostBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 posts 已废弃，请使用 bop_entries API")


@router.patch("/posts/{gid}", status_code=410)
def update_post(gid: str, body: UpdatePostBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 posts 已废弃，请使用 bop_entries API")


@router.delete("/posts/{gid}", status_code=410)
def delete_post(gid: str, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 posts 已废弃，请使用 bop_entries API")


@router.post("/posts/{post_gid}/operations", status_code=410)
def create_operation(post_gid: str, body: CreateOperationBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 operations 已废弃，请使用 bop_entries API")


@router.patch("/operations/{gid}", status_code=410)
def update_operation(gid: str, body: UpdateOperationBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 operations 已废弃，请使用 bop_entries API")


@router.delete("/operations/{gid}", status_code=410)
def delete_operation(gid: str, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 operations 已废弃，请使用 bop_entries API")


@router.post("/operations/{op_gid}/steps", status_code=410)
def create_step(op_gid: str, body: CreateStepBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 steps 已废弃，请使用 bop_entries API")


@router.patch("/steps/{gid}", status_code=410)
def update_step(gid: str, body: UpdateStepBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 steps 已废弃，请使用 bop_entries API")


@router.delete("/steps/{gid}", status_code=410)
def delete_step(gid: str, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 steps 已废弃，请使用 bop_entries API")


@router.get("/operations/{op_gid}/resources", status_code=410)
def list_op_resources(op_gid: str, _u=Depends(_READ)):
    raise HTTPException(410, "V1 operation_resources 已废弃，请使用 bop_entry_links API")


@router.post("/operations/{op_gid}/resources", status_code=410)
def create_op_resource(op_gid: str, body: CreateResourceBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 operation_resources 已废弃，请使用 bop_entry_links API")


@router.delete("/resources/{gid}", status_code=410)
def delete_resource(gid: str, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 operation_resources 已废弃，请使用 bop_entry_links API")


@router.get("/operations/{gid}/drift-check", status_code=410)
def drift_check(gid: str, _u=Depends(_READ)):
    raise HTTPException(410, "V1 operations drift-check 已废弃")


@router.post("/operations/{gid}/reset-fields", status_code=410)
def reset_fields(gid: str, body: ResetFieldsBody, _u=Depends(_WRITE)):
    raise HTTPException(410, "V1 operations reset-fields 已废弃")
