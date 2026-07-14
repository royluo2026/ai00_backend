"""
backend/routers/_bop/fork.py
──────────────────────────────
BOP Fork（可控字段 fork / clone）+ Fork 预设 CRUD + Smart Fork + Stage-Advance。
"""
import json
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.utils.gid import next_gid

from ._constants import (
    _WRITE, _READ,
    _VER_COLS, _VER_KEYS, _PRESET_COLS, _PRESET_KEYS,
    _AI00_LEVEL, _FORK_USER_FIELDS,
    _DEPTH_CUTOFF, _DEEP_COPY_ENTITY_TABLES,
    _SHARED_ENTITY_LINK_TYPES, _SKIP_LINK_TYPES,
)
from ._helpers import (
    _not_found, _sync_child_vpps,
    _snapshot_links, _deep_copy_entity, _copy_entity_for_fork,
)

router = APIRouter(prefix="/api/bop", tags=["bop"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class ForkBody(BaseModel):
    target_version_tag:      str
    target_bop_name:         str = ''
    target_version_family_gid: Optional[str] = None
    change_note:             Optional[str] = None
    include_node_types:      Optional[List[str]] = None
    field_rules:             Dict[str, Literal['inherit', 'reset']] = {}
    meta_key_rules:          Dict[str, Literal['inherit', 'reset']] = {}
    version_type:            Optional[str] = None


class CreateForkPresetBody(BaseModel):
    name:                str
    description:         Optional[str] = None
    include_node_types:  Optional[List[str]] = None
    field_rules:         Dict[str, Literal['inherit', 'reset']] = {}
    meta_key_rules:      Dict[str, Literal['inherit', 'reset']] = {}
    team_gid:            Optional[str] = None


class UpdateForkPresetBody(BaseModel):
    name:                Optional[str] = None
    description:         Optional[str] = None
    include_node_types:  Optional[List[str]] = None
    field_rules:         Optional[Dict[str, Literal['inherit', 'reset']]] = None
    meta_key_rules:      Optional[Dict[str, Literal['inherit', 'reset']]] = None


class SmartForkBody(BaseModel):
    mode: Optional[Literal['minor_facelift', 'new_model']] = None
    target_version_tag: str
    target_bop_name: str = ''
    changed_part_gids: List[str] = []
    pbom_version_gid: Optional[str] = None
    copy_depth: Optional[str] = None


class StageAdvanceBody(BaseModel):
    pbom_version_gid: str
    stage_name: str


# ══════════════════════════════════════════════════════════════
# Fork
# ══════════════════════════════════════════════════════════════

@router.post("/versions/{source_gid}/fork", status_code=201)
def fork_version(source_gid: str, body: ForkBody, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (source_gid,))
            src_ver = cur.fetchone()
            if not src_ver:
                raise HTTPException(404, f"源版本 {source_gid} 不存在")
            src_ver = dict(src_ver)

            if body.include_node_types:
                placeholders = ','.join(['%s'] * len(body.include_node_types))
                cur.execute(
                    f"SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    f" title, vpps, vpps_desc, parent_bop_title, child_vpps,"
                    f" owner_gid, meta"
                    f" FROM workmanship_bop_bop_entries"
                    f" WHERE version_gid=%s AND is_deleted = FALSE"
                    f"   AND node_type IN ({placeholders})"
                    f" ORDER BY sort_order",
                    [source_gid] + body.include_node_types,
                )
            else:
                cur.execute(
                    "SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, parent_bop_title, child_vpps,"
                    " owner_gid, meta"
                    " FROM workmanship_bop_bop_entries"
                    " WHERE version_gid=%s AND is_deleted = FALSE"
                    " ORDER BY sort_order",
                    (source_gid,),
                )
            src_entries = [dict(r) for r in cur.fetchall()]

            new_ver_gid = str(next_gid())
            family_gid  = body.target_version_family_gid or new_ver_gid
            bop_name    = body.target_bop_name or src_ver.get('bop_name', '')
            cur.execute(
                f"INSERT INTO workmanship_bop_bop_versions "
                f"(gid,version_tag,bop_name,version_family_gid,"
                f" project_gid,factory_gid,vehicle_model_gid,maturity,takt_time,"
                f" status,meta,lifecycle_phase,lifecycle_state,visibility,parent_version_gid,change_note,version_type) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_ver_gid, body.target_version_tag, bop_name, family_gid,
                 src_ver.get('project_gid'), src_ver.get('factory_gid'),
                 src_ver.get('vehicle_model_gid'), src_ver.get('maturity', 'concept'),
                 src_ver.get('takt_time', 60),
                 'active', json.dumps({}), 'init', json.dumps({}), 'team',
                 source_gid, body.change_note, body.version_type)
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (new_ver_gid,))
            new_ver = dict(cur.fetchone())

            if not src_entries:
                conn.commit()
                return {"data": new_ver, "entries_count": 0}

            gid_map = {e['gid']: str(next_gid()) for e in src_entries}

            # 拓扑排序：保证父节点先于子节点插入（避免 parent_gid FK 约束违反）
            entry_by_gid = {e['gid']: e for e in src_entries}
            topo_sorted: list = []
            visited: set = set()

            def _topo_visit(gid):
                if gid in visited:
                    return
                visited.add(gid)
                e = entry_by_gid.get(gid)
                if e and e.get('parent_gid') and e['parent_gid'] in entry_by_gid:
                    _topo_visit(e['parent_gid'])
                if e:
                    topo_sorted.append(e)

            for e in src_entries:
                _topo_visit(e['gid'])

            rules   = body.field_rules
            mk_rules = body.meta_key_rules
            default_meta_rule = mk_rules.get('*', 'inherit')

            for e in topo_sorted:
                new_gid    = gid_map[e['gid']]
                new_parent = gid_map.get(e['parent_gid']) if e['parent_gid'] else None

                def _fval(field):
                    rule = rules.get(field, 'inherit')
                    return e.get(field) if rule == 'inherit' else None

                src_meta = e.get('meta') or {}
                if isinstance(src_meta, str):
                    try:
                        src_meta = json.loads(src_meta)
                    except Exception:
                        src_meta = {}
                if mk_rules:
                    new_meta = {}
                    for k, v in src_meta.items():
                        key_rule = mk_rules.get(k, default_meta_rule)
                        if key_rule == 'inherit':
                            new_meta[k] = v
                else:
                    meta_rule = rules.get('meta', 'inherit')
                    new_meta = src_meta if meta_rule == 'inherit' else {}

                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entries "
                    "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, parent_bop_title, child_vpps,"
                    " owner_gid, meta) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (new_gid, new_ver_gid, new_parent,
                     e['node_type'], e['sort_order'], e.get('level', 0),
                     _AI00_LEVEL.get(e['node_type']),
                     _fval('title'), _fval('vpps'), _fval('vpps_desc'),
                     _fval('parent_bop_title'),
                     json.dumps(e.get('child_vpps') or []),
                     _fval('owner_gid'),
                     json.dumps(new_meta))
                )

            conn.commit()
            return {"data": new_ver, "entries_count": len(gid_map)}


# ══════════════════════════════════════════════════════════════
# Fork 预设 CRUD
# ══════════════════════════════════════════════════════════════

@router.get("/fork-presets")
def list_fork_presets(team_gid: Optional[str] = None, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if team_gid:
                cur.execute(
                    f"SELECT {_PRESET_COLS} FROM workmanship_bop_bop_fork_presets "
                    f"WHERE team_gid=%s OR team_gid IS NULL ORDER BY created_at",
                    (team_gid,)
                )
            else:
                cur.execute(
                    f"SELECT {_PRESET_COLS} FROM workmanship_bop_bop_fork_presets ORDER BY created_at"
                )
            from ._helpers import _rows
            return {"data": _rows(cur, _PRESET_KEYS)}


@router.post("/fork-presets", status_code=201)
def create_fork_preset(body: CreateForkPresetBody, _u=Depends(_WRITE)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO workmanship_bop_bop_fork_presets "
                f"(gid,name,description,include_node_types,field_rules,meta_key_rules,team_gid,created_by) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.name, body.description,
                 json.dumps(body.include_node_types),
                 json.dumps(body.field_rules),
                 json.dumps(body.meta_key_rules),
                 body.team_gid, _u.get('gid') if isinstance(_u, dict) else None)
            )
            conn.commit()
            cur.execute(f"SELECT {_PRESET_COLS} FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
            from ._helpers import _row
            return {"data": _row(cur, _PRESET_KEYS)}


@router.patch("/fork-presets/{gid}")
def update_fork_preset(gid: str, body: UpdateForkPresetBody, _u=Depends(_WRITE)):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "无更新字段")
    set_parts, vals = [], []
    for k, v in data.items():
        if k in ('field_rules', 'meta_key_rules', 'include_node_types'):
            set_parts.append(f"{k}=%s")
            vals.append(json.dumps(v))
        else:
            set_parts.append(f"{k}=%s")
            vals.append(v)
    set_parts.append("updated_at=NOW()")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_bop_bop_fork_presets SET {', '.join(set_parts)} WHERE gid=%s",
                vals + [gid]
            )
            cur.execute(f"SELECT {_PRESET_COLS} FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
            from ._helpers import _row
            row = _row(cur, _PRESET_KEYS)
            if not row: _not_found(gid)
            conn.commit()
            return {"data": row}


@router.get("/fork-presets/{gid}")
def get_fork_preset(gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_PRESET_COLS} FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row: _not_found(gid)
            return {"data": dict(row)}


@router.delete("/fork-presets/{gid}", status_code=204)
def delete_fork_preset(gid: str, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
            if cur.rowcount == 0: _not_found(gid)
            conn.commit()


# ══════════════════════════════════════════════════════════════
# Smart Fork
# ══════════════════════════════════════════════════════════════

@router.post("/versions/{source_gid}/smart-fork", status_code=201)
def smart_fork_version(source_gid: str, body: SmartForkBody, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (source_gid,))
            src_ver = cur.fetchone()
            if not src_ver:
                raise HTTPException(404, f"源版本 {source_gid} 不存在")
            src_ver = dict(src_ver)
            project_gid = src_ver.get('project_gid')

            pbom_version_gid = body.pbom_version_gid
            if pbom_version_gid:
                cur.execute("SELECT status FROM pbom.pbom_versions WHERE gid=%s", (pbom_version_gid,))
                pbom_ver = cur.fetchone()
                if not pbom_ver or pbom_ver['status'] != 'ready':
                    raise HTTPException(400, "PBOM 版本尚未就绪（status != 'ready'）")

            new_ver_gid = str(next_gid())
            bop_name = body.target_bop_name or src_ver.get('bop_name', '')
            fork_note = f'smart-fork/{body.copy_depth or body.mode}'
            cur.execute(
                f"INSERT INTO workmanship_bop_bop_versions "
                f"(gid,version_tag,bop_name,version_family_gid,"
                f" project_gid,factory_gid,vehicle_model_gid,maturity,takt_time,"
                f" parent_version_gid,change_note,version_type,pbom_version_gid) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_ver_gid, body.target_version_tag, bop_name, new_ver_gid,
                 project_gid, src_ver.get('factory_gid'),
                 src_ver.get('vehicle_model_gid'), src_ver.get('maturity', 'concept'),
                 src_ver.get('takt_time', 60),
                 source_gid, fork_note, 'working', pbom_version_gid)
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (new_ver_gid,))
            new_ver = dict(cur.fetchone())

            cur.execute(
                "SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
                " title, vpps, vpps_desc, parent_bop_title, child_vpps, owner_gid, meta"
                " FROM workmanship_bop_bop_entries"
                " WHERE version_gid=%s AND is_deleted = FALSE"
                " ORDER BY sort_order",
                (source_gid,),
            )
            src_entries = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT gid, entry_gid, link_type, entity_gid, is_primary,"
                " is_inherited, snapshot_data"
                " FROM workmanship_bop_bop_entry_links"
                " WHERE version_gid=%s AND is_deleted = FALSE",
                (source_gid,),
            )
            src_links = [dict(r) for r in cur.fetchall()]

            if not src_entries:
                conn.commit()
                return {"data": new_ver, "entries_count": 0}

            gid_map: Dict[str, str] = {e['gid']: str(next_gid()) for e in src_entries}

            if body.copy_depth and body.copy_depth in _DEPTH_CUTOFF:
                keep_levels = _DEPTH_CUTOFF[body.copy_depth]
                max_level = max(keep_levels)

                inserted_entry_gids: set = set()
                for e in src_entries:
                    ai00_lv = _AI00_LEVEL.get(e['node_type'], 0)
                    new_gid    = gid_map[e['gid']]
                    new_parent = gid_map.get(e['parent_gid']) if e['parent_gid'] else None

                    if ai00_lv > max_level:
                        cur.execute(
                            "INSERT INTO workmanship_bop_bop_entries "
                            "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                            " title, vpps, parent_bop_title, child_vpps) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (new_gid, new_ver_gid, new_parent,
                             e['node_type'], e['sort_order'], e.get('level', 0),
                             ai00_lv,
                             e.get('title'), e.get('vpps'),
                             e.get('parent_bop_title'),
                             json.dumps(e.get('child_vpps') or []))
                        )
                    else:
                        cur.execute(
                            "INSERT INTO workmanship_bop_bop_entries "
                            "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                            " title, vpps, vpps_desc, parent_bop_title, child_vpps,"
                            " owner_gid, meta) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (new_gid, new_ver_gid, new_parent,
                             e['node_type'], e['sort_order'], e.get('level', 0),
                             ai00_lv,
                             e.get('title'), e.get('vpps'), e.get('vpps_desc'),
                             e.get('parent_bop_title'),
                             json.dumps(e.get('child_vpps') or []),
                             e.get('owner_gid'),
                             json.dumps(e.get('meta') or {}))
                        )
                    inserted_entry_gids.add(new_gid)

                for lnk in src_links:
                    if lnk['link_type'] in _SKIP_LINK_TYPES:
                        continue
                    new_entry_gid = gid_map.get(lnk['entry_gid'])
                    if not new_entry_gid or new_entry_gid not in inserted_entry_gids:
                        continue
                    if lnk['link_type'] in _SHARED_ENTITY_LINK_TYPES:
                        new_ent_gid = lnk['entity_gid']
                    else:
                        new_ent_gid = _deep_copy_entity(
                            cur, lnk['link_type'], lnk['entity_gid'], project_gid
                        )
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entry_links "
                        "(gid, entry_gid, version_gid, link_type, entity_gid,"
                        " is_primary, is_inherited) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (str(next_gid()), new_entry_gid, new_ver_gid,
                         lnk['link_type'], new_ent_gid,
                         lnk['is_primary'], lnk.get('is_inherited', False)),
                    )

                parent_gids_to_sync: set = set()
                for e in src_entries:
                    if e.get('parent_gid') and gid_map.get(e['parent_gid']):
                        parent_gids_to_sync.add(gid_map[e['parent_gid']])
                for pg in parent_gids_to_sync:
                    _sync_child_vpps(cur, pg, new_ver_gid)

            elif body.mode == 'minor_facelift':
                affected_step_entity_gids: set = set()
                if body.changed_part_gids:
                    _ph = ",".join(["%s"] * len(body.changed_part_gids))
                    cur.execute(
                        f"SELECT gid FROM workmanship_bop_bop_steps"
                        f" WHERE vpps_part IN ({_ph})"
                        f"   AND project_gid=%s",
                        list(body.changed_part_gids) + [project_gid],
                    )
                    affected_step_entity_gids = {r['gid'] for r in cur.fetchall()}

                affected_entry_gids: set = set()
                for lnk in src_links:
                    if lnk['link_type'] == 'bop_steps' and lnk['entity_gid'] in affected_step_entity_gids:
                        affected_entry_gids.add(lnk['entry_gid'])

                for e in src_entries:
                    new_gid    = gid_map[e['gid']]
                    new_parent = gid_map.get(e['parent_gid']) if e['parent_gid'] else None
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entries "
                        "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                        " title, vpps, vpps_desc, parent_bop_title, child_vpps,"
                        " owner_gid, meta) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (new_gid, new_ver_gid, new_parent,
                         e['node_type'], e['sort_order'], e.get('level', 0),
                         _AI00_LEVEL.get(e['node_type']),
                         e.get('title'), e.get('vpps'), e.get('vpps_desc'),
                         e.get('parent_bop_title'),
                         json.dumps(e.get('child_vpps') or []),
                         e.get('owner_gid'),
                         json.dumps(e.get('meta') or {}))
                    )

                for lnk in src_links:
                    new_entry_gid = gid_map.get(lnk['entry_gid'])
                    if not new_entry_gid:
                        continue
                    new_ent_gid = _copy_entity_for_fork(
                        cur, lnk['link_type'], lnk['entity_gid'], project_gid
                    )
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entry_links "
                        "(gid, entry_gid, version_gid, link_type, entity_gid,"
                        " is_primary, is_inherited, snapshot_data) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (str(next_gid()), new_entry_gid, new_ver_gid,
                         lnk['link_type'], new_ent_gid,
                         lnk['is_primary'], lnk.get('is_inherited', False),
                         json.dumps(lnk['snapshot_data']) if lnk.get('snapshot_data') else None),
                    )

                if affected_entry_gids:
                    new_affected = {gid_map[old] for old in affected_entry_gids if old in gid_map}
                    to_delete: list = []
                    for aff_gid in new_affected:
                        q = [aff_gid]
                        while q:
                            p = q.pop()
                            cur.execute(
                                "SELECT e.gid FROM workmanship_bop_bop_entries e"
                                " WHERE e.parent_gid=%s AND e.version_gid=%s AND e.is_deleted=FALSE",
                                (p, new_ver_gid),
                            )
                            for row in cur.fetchall():
                                c = row['gid']
                                cur.execute(
                                    "SELECT link_type FROM workmanship_bop_bop_entry_links"
                                    " WHERE entry_gid=%s AND is_primary=TRUE",
                                    (c,),
                                )
                                lt_row = cur.fetchone()
                                is_physical = lt_row and lt_row['link_type'].startswith('physical_')
                                if not is_physical:
                                    to_delete.append(c)
                                    q.append(c)
                    if to_delete:
                        _ph = ",".join(["%s"] * len(to_delete))
                        cur.execute(
                            f"UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW()"
                            f" WHERE gid IN ({_ph}) AND version_gid=%s",
                            to_delete + [new_ver_gid],
                        )

            elif body.mode == 'new_model':
                _KEEP_FULL = {'line_process', 'station_process'}
                _KEEP_SKELETON = {'process'}
                _DROP_DETAIL = {'operation', 'operator_process'}

                inserted_entry_gids: set = set()

                for e in src_entries:
                    nt = e['node_type']
                    new_gid    = gid_map[e['gid']]
                    new_parent = gid_map.get(e['parent_gid']) if e['parent_gid'] else None

                    if nt in _DROP_DETAIL:
                        continue

                    if nt in _KEEP_SKELETON:
                        cur.execute(
                            "INSERT INTO workmanship_bop_bop_entries "
                            "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                            " title, vpps, parent_bop_title, child_vpps) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (new_gid, new_ver_gid, new_parent,
                             nt, e['sort_order'], e.get('level', 0),
                             _AI00_LEVEL.get(nt),
                             e.get('title'), e.get('vpps'),
                             e.get('parent_bop_title'),
                             json.dumps(e.get('child_vpps') or []))
                        )
                    else:
                        cur.execute(
                            "INSERT INTO workmanship_bop_bop_entries "
                            "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                            " title, vpps, vpps_desc, parent_bop_title, child_vpps,"
                            " owner_gid, meta) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (new_gid, new_ver_gid, new_parent,
                             nt, e['sort_order'], e.get('level', 0),
                             _AI00_LEVEL.get(nt),
                             e.get('title'), e.get('vpps'), e.get('vpps_desc'),
                             e.get('parent_bop_title'),
                             json.dumps(e.get('child_vpps') or []),
                             e.get('owner_gid'),
                             json.dumps(e.get('meta') or {}))
                        )
                    inserted_entry_gids.add(new_gid)

                _KEEP_LINK_TYPES = {
                    'bop_line', 'bop_station', 'bop_process',
                    'physical_equipment', 'physical_tool', 'physical_fixture', 'physical_station',
                    'project_equipment', 'project_tooling', 'project_tools',
                    'floor_height', 'control_plan', 'process_chart', 'jack_pos',
                }
                for lnk in src_links:
                    if lnk['link_type'] not in _KEEP_LINK_TYPES:
                        continue
                    new_entry_gid = gid_map.get(lnk['entry_gid'])
                    if not new_entry_gid or new_entry_gid not in inserted_entry_gids:
                        continue
                    new_ent_gid = _copy_entity_for_fork(
                        cur, lnk['link_type'], lnk['entity_gid'], project_gid
                    )
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entry_links "
                        "(gid, entry_gid, version_gid, link_type, entity_gid,"
                        " is_primary, is_inherited) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (str(next_gid()), new_entry_gid, new_ver_gid,
                         lnk['link_type'], new_ent_gid,
                         lnk['is_primary'], lnk.get('is_inherited', False)),
                    )

            conn.commit()
            return {"data": new_ver, "entries_count": len(gid_map)}


# ══════════════════════════════════════════════════════════════
# Stage Advance
# ══════════════════════════════════════════════════════════════

@router.post("/versions/{src_gid}/stage-advance", status_code=201)
def stage_advance(src_gid: str, body: StageAdvanceBody, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (src_gid,))
            src_ver = cur.fetchone()
            if not src_ver:
                raise HTTPException(404, f"源版本 {src_gid} 不存在")
            src_ver = dict(src_ver)
            if src_ver.get('status') != 'active':
                raise HTTPException(400, f"只有 active 状态的版本可以推进阶段，当前: {src_ver.get('status')}")

            cur.execute("SELECT status FROM pbom.pbom_versions WHERE gid=%s", (body.pbom_version_gid,))
            pbom_ver = cur.fetchone()
            if not pbom_ver or pbom_ver['status'] != 'ready':
                raise HTTPException(400, "PBOM 版本尚未就绪（status != 'ready'）")

            _snapshot_links(cur, src_gid)
            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET status='baseline', frozen_at=NOW(), updated_at=NOW() "
                "WHERE gid=%s",
                (src_gid,)
            )

            new_ver_gid = str(next_gid())
            cur.execute(
                f"INSERT INTO workmanship_bop_bop_versions "
                f"(gid,version_tag,bop_name,version_family_gid,"
                f" project_gid,factory_gid,vehicle_model_gid,maturity,takt_time,"
                f" parent_version_gid,change_note,version_type,pbom_version_gid) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_ver_gid, body.stage_name,
                 src_ver.get('bop_name', ''),
                 src_ver.get('version_family_gid', new_ver_gid),
                 src_ver.get('project_gid'), src_ver.get('factory_gid'),
                 src_ver.get('vehicle_model_gid'), src_ver.get('maturity', 'concept'),
                 src_ver.get('takt_time', 60),
                 src_gid, f'stage-advance/{body.stage_name}',
                 'working', body.pbom_version_gid)
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (new_ver_gid,))
            new_ver = dict(cur.fetchone())

            cur.execute(
                "SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
                " title, vpps, vpps_desc, parent_bop_title, child_vpps, owner_gid, meta"
                " FROM workmanship_bop_bop_entries"
                " WHERE version_gid=%s AND is_deleted = FALSE"
                " ORDER BY sort_order",
                (src_gid,),
            )
            src_entries = [dict(r) for r in cur.fetchall()]

            if not src_entries:
                conn.commit()
                return {"data": new_ver, "entries_count": 0}

            gid_map_sa: Dict[str, str] = {e['gid']: str(next_gid()) for e in src_entries}

            for e in src_entries:
                new_gid_sa = gid_map_sa[e['gid']]
                new_parent_sa = gid_map_sa.get(e['parent_gid']) if e['parent_gid'] else None
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entries "
                    "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, parent_bop_title, child_vpps, owner_gid, meta) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (new_gid_sa, new_ver_gid, new_parent_sa,
                     e['node_type'], e['sort_order'], e.get('level', 0),
                     _AI00_LEVEL.get(e['node_type']),
                     e.get('title'), e.get('vpps'), e.get('vpps_desc'),
                     e.get('parent_bop_title'),
                     json.dumps(e.get('child_vpps') or []),
                     e.get('owner_gid'), json.dumps(e.get('meta') or {}))
                )

            cur.execute(
                "SELECT entry_gid, link_type, entity_gid, is_primary, is_inherited"
                " FROM workmanship_bop_bop_entry_links"
                " WHERE version_gid=%s AND is_deleted = FALSE",
                (src_gid,),
            )
            src_links_sa = [dict(r) for r in cur.fetchall()]

            for lnk in src_links_sa:
                if lnk['link_type'] in _SKIP_LINK_TYPES:
                    continue
                new_entry_gid_sa = gid_map_sa.get(lnk['entry_gid'])
                if not new_entry_gid_sa:
                    continue
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entry_links "
                    "(gid, entry_gid, version_gid, link_type, entity_gid,"
                    " is_primary, is_inherited) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (str(next_gid()), new_entry_gid_sa, new_ver_gid,
                     lnk['link_type'], lnk['entity_gid'],
                     lnk['is_primary'], lnk.get('is_inherited', False)),
                )

            conn.commit()
            return {"data": new_ver, "entries_count": len(gid_map_sa)}
