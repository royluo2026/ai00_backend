"""
backend/routers/_bop/entries.py
────────────────────────────────
BOP 条目树 CRUD + import-tc + auto-link + entry-links CRUD + link-summary + entity-detail + PBOM 搜索。
"""
import base64 as _b64
import json
import logging
import threading
import traceback
import uuid as _uuid
from datetime import datetime, date
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from ...data.connection import get_conn
from backend.platform_sdk.ids import next_gid
from backend.platform_sdk.identity import resolve_identity_labels

from ._constants import (
    _WRITE, _READ, _SUPER_ADMIN,
    _ENTRY_LIST_SQL, _ENTRY_KEYS, _ENTRY_BY_GID_SQL,
    _AI00_LEVEL, _BOP_PICS_DIR, _BOP_PICS_MAX,
    _PROCESS_ENTITY_MAP, _PART_NODE_TYPES, _LINK_TARGET_TABLE, _LINK_TARGET_TABLES,
    _DEEP_COPY_ENTITY_TABLES, _GID_RESOLVE_MAP,
)
from ._helpers import (
    _row, _rows, _not_found,
    _check_version_frozen, _parent_level,
    _sync_child_vpps,
    _do_copy, _check_auto_link_rules,
    _get_line_gid, _log_entry_op, _check_line_editable,
    legacy_entries_max_from_env,
)
from . import _history

_log = logging.getLogger(__name__)

_LEGACY_ENTRIES_MAX = legacy_entries_max_from_env()
_LEGACY_ENTRIES_USAGE = {"served": 0, "rejected": 0}
_LEGACY_ENTRIES_USAGE_LOCK = threading.Lock()


def _record_legacy_entries_usage(outcome: str) -> None:
    with _LEGACY_ENTRIES_USAGE_LOCK:
        _LEGACY_ENTRIES_USAGE[outcome] += 1


def legacy_entries_usage_snapshot() -> dict[str, int]:
    """Return process-local aggregate migration counters without request labels."""
    with _LEGACY_ENTRIES_USAGE_LOCK:
        return dict(_LEGACY_ENTRIES_USAGE)

router = APIRouter(prefix="/api/bop", tags=["bop"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class CreateEntryBody(BaseModel):
    version_gid:      str = ''
    bop_version_gid:  Optional[str] = None  # 前端别名
    parent_gid:       Optional[str] = None
    node_type:        str = 'process'
    sort_order:       float = 0
    title:            str = ''
    vpps:             Optional[str] = None
    vpps_desc:        Optional[str] = None
    parent_bop_title: Optional[str] = None
    position:         Optional[str] = None  # operator_process 位置 A-F → bop_operator.ext.position
    meta:             Optional[dict] = None  # 创建时携带的 meta 初始值

    def get_version_gid(self) -> str:
        return self.bop_version_gid or self.version_gid


class UpdateEntryBody(BaseModel):
    parent_gid:       Optional[str]   = None
    node_type:        Optional[str]   = None
    sort_order:       Optional[float] = None
    title:            Optional[str]   = None
    vpps:             Optional[str]   = None
    vpps_desc:        Optional[str]   = None
    parent_bop_title: Optional[str]   = None
    process_flow_pic: Optional[list]  = None
    cad_sim_pics:     Optional[list]  = None
    meta:             Optional[dict]  = None


class ImportTcBody(BaseModel):
    rows: list


class BopPicUploadBody(BaseModel):
    filename: str
    mime: str
    data_b64: str


def _normalize_bop_pic_items(items):
    # MySQL JSON 列返回的是字符串，先 parse
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []
    out = []
    for item in items or []:
        if isinstance(item, dict):
            pic = dict(item)
            url = str(pic.get('url') or '').strip()
            object_key = str(pic.get('object_key') or '').strip().lstrip('/')
            storage = str(pic.get('storage') or '').strip()
            if url or object_key:
                out.append({
                    'url': url,
                    'object_key': object_key,
                    'storage': storage,
                })
        elif isinstance(item, str):
            url = item.strip()
            if url:
                out.append({'url': url, 'object_key': '', 'storage': ''})
    return out


def _resolve_bop_pic_items(items):
    from backend.platform_sdk import ois_storage as _ois_storage

    resolved = []
    for pic in _normalize_bop_pic_items(items):
        if pic.get('storage') == 'ois' and pic.get('object_key'):
            access_url = _ois_storage.generate_access_url(pic['object_key'])
            if access_url:
                resolved.append({**pic, 'url': access_url})
                continue
        resolved.append(pic)
    return resolved


class CreateEntryLinkBody(BaseModel):
    entry_gid: str
    link_type: str
    entity_gid: str
    is_primary: bool = False


class EntityPatchBody(BaseModel):
    link_type: str
    ref_gid: str
    fields: Dict[str, Optional[str]]


class AutoLinkBody(BaseModel):
    step: str = 'all'
    mode: str = 'incremental'


# ══════════════════════════════════════════════════════════════
# BOP 条目 CRUD
# ══════════════════════════════════════════════════════════════

@router.get("/versions/{version_gid}/alt-hier")
def get_alt_hier(version_gid: str, _u=Depends(_READ)):
    """返回 BOP 树结构，每个条目附带其关联 pbom_part 的 catia_occurrence_name 列表。
    用于 cad_sim 页"备选层次结构"与 VisMockup 节点的 catiaOccurrenceName 匹配。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.gid, e.parent_gid, e.node_type, e.sort_order,
                       e.title, e.vpps, e.level, e.ai00_level,
                       p.gid        AS part_gid,
                       p.part_no,
                       p.catia_occurrence_name,
                       p.title      AS part_name,
                       p.vpps       AS part_vpps,
                       p.quantity
                FROM workmanship_bop_bop_entries e
                LEFT JOIN workmanship_bop_bop_entry_links l
                    ON l.entry_gid = e.gid AND l.link_type = 'pbom_part'
                LEFT JOIN workmanship_bop_pbom p ON p.gid = l.entity_gid
                WHERE e.version_gid = %s AND e.is_deleted = FALSE
                ORDER BY e.sort_order 
                """,
                (version_gid,),
            )
            rows = cur.fetchall()

    # 按 entry_gid 聚合：每个 entry 可能有多个 pbom_part 行
    entries: dict = {}
    for r in rows:
        gid = r["gid"]
        if gid not in entries:
            entries[gid] = {
                "gid":        gid,
                "parent_gid": r["parent_gid"],
                "node_type":  r["node_type"],
                "sort_order": r["sort_order"],
                "title":      r["title"],
                "vpps":       r["vpps"],
                "level":      r["level"],
                "ai00_level": r["ai00_level"],
                "parts":      [],
            }
        if r["part_gid"]:
            entries[gid]["parts"].append({
                "gid":      r["part_gid"],
                "part_no":  r["part_no"] or "",
                "catia_occ": r["catia_occurrence_name"] or "",
                "name":     r["part_name"] or "",
                "vpps":     r["part_vpps"] or "",
                "quantity": r["quantity"],
            })

    return {"entries": list(entries.values())}


@router.get("/versions/{version_gid}/line-op-catia-parts")
def get_line_op_catia_parts(
    version_gid: str,
    line_entry_gid: str = Query(...),
    _u=Depends(_READ),
):
    """返回指定线体节点下所有 operation 条目及其关联零件的 catia_occurrence_name 列表。
    按 sort_order DESC 排序（倒序 = 最后装的最先拆），供一键截图流程使用。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH RECURSIVE desc_entries AS (
                    SELECT gid, title, sort_order, node_type
                    FROM workmanship_bop_bop_entries
                    WHERE gid = %s AND is_deleted = FALSE
                    UNION ALL
                    SELECT b.gid, b.title, b.sort_order, b.node_type
                    FROM workmanship_bop_bop_entries b
                    JOIN desc_entries d ON b.parent_gid = d.gid
                    WHERE b.is_deleted = FALSE
                )
                SELECT
                    d.gid  AS bop_entry_gid,
                    d.title,
                    d.sort_order,
                    IFNULL(
                        JSON_ARRAYAGG(
                            CASE WHEN p.catia_occurrence_name IS NOT NULL
                                      AND p.catia_occurrence_name != ''
                                 THEN p.catia_occurrence_name END
                        ),
                        JSON_ARRAY()
                    ) AS catia_names
                FROM desc_entries d
                JOIN workmanship_bop_bop_entry_links bel
                    ON bel.entry_gid = d.gid AND bel.link_type = 'pbom_part'
                    AND bel.deleted_at IS NULL
                LEFT JOIN workmanship_bop_pbom p ON p.gid = bel.entity_gid
                WHERE d.node_type = 'operation'
                GROUP BY d.gid, d.title, d.sort_order
                ORDER BY d.sort_order DESC 
                """,
                (line_entry_gid,),
            )
            rows = cur.fetchall()

    data = []
    for r in rows:
        catia_names = r['catia_names']
        if isinstance(catia_names, str):
            import json as _j
            catia_names = _j.loads(catia_names)
        data.append({
            'bop_entry_gid': r['bop_entry_gid'],
            'title':         r['title'] or '',
            'sort_order':    r['sort_order'],
            'catia_names':   [n for n in (catia_names or []) if n],
        })
    return {'ok': True, 'data': data}


@router.get("/versions/{version_gid}/entries")
def list_entries(version_gid: str, response: Response, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS entry_count "
                "FROM workmanship_bop_bop_entries "
                "WHERE version_gid=%s AND is_deleted=FALSE",
                (version_gid,),
            )
            count_row = cur.fetchone()
            entry_count = int(count_row["entry_count"] if count_row else 0)
            if entry_count > _LEGACY_ENTRIES_MAX:
                _record_legacy_entries_usage("rejected")
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "dataset_too_large_use_paged_capability",
                        "details": {
                            "entry_count": entry_count,
                            "configured_limit": _LEGACY_ENTRIES_MAX,
                            "replacement_capabilities": [
                                "craft.bop.structure.outline.get@1",
                                "craft.bop.work_package.get@2",
                                "craft.bop.entry.detail.get@1",
                            ],
                        },
                    },
                )
            response.headers["Deprecation"] = "true"
            _record_legacy_entries_usage("served")
            cur.execute(_ENTRY_LIST_SQL, (version_gid, version_gid))
            rows = _rows(cur, _ENTRY_KEYS)
            for row in rows:
                row['process_flow_pic'] = _resolve_bop_pic_items(row.get('process_flow_pic') or [])
                row['process_chart_pic'] = _resolve_bop_pic_items(row.get('process_chart_pic') or [])
            return {"data": rows}


@router.get("/versions/{version_gid}/pbom")
def get_version_pbom(version_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pe.gid, pe.title, pe.vpps, pe.parent_part_gid,
                       pe.node_type, pe.bom_row_id, pe.seq_no,
                       pe.quantity, pe.unit, pe.part_number,
                       pe.created_at, pe.updated_at
                FROM workmanship_bop_pbom pe
                JOIN workmanship_bop_bop_entry_links l ON l.entity_gid = pe.gid
                JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid
                WHERE e.version_gid = %s
                  AND l.link_type = 'pbom_part'
                  AND e.is_deleted = FALSE
                ORDER BY pe.seq_no
                """,
                (version_gid,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": rows}


@router.get("/versions/{version_gid}/linked-parts")
def get_version_linked_parts(version_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pe.gid, pe.title AS name, pe.parent_gid,
                       pe.part_no, pe.quantity, pe.unit,
                       pe.snapshot_gid, pe.material, pe.meta,
                       l.entry_gid, l.gid AS link_gid,
                       pe.created_at
                FROM workmanship_bop_bop_entry_links l
                JOIN workmanship_bop_pbom pe ON pe.gid = l.entity_gid
                JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid
                WHERE e.version_gid = %s
                  AND l.link_type = 'pbom_part'
                  AND l.is_primary = TRUE
                  AND e.is_deleted = FALSE
                ORDER BY pe.part_no
                """,
                (version_gid,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": rows}


@router.get("/entries/search")
def search_entries(
    q: Optional[str] = Query(None),
    node_types: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    _u=Depends(_READ),
):
    type_list = [t.strip() for t in node_types.split(",")] if node_types else None
    like = f"%{q}%" if q else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            if type_list:
                placeholders = ",".join(["%s"] * len(type_list))
                type_clause = f"AND e.node_type IN ({placeholders})"
                type_params = type_list
            else:
                type_clause = ""
                type_params = []
            like_clause = "AND COALESCE(e.title,'') LIKE %s" if like else ""
            like_params = [like] if like else []
            cur.execute(
                f"""
                SELECT e.gid,
                       COALESCE(e.title, '') AS title,
                       e.node_type,
                       v.gid AS version_gid, v.version_tag
                FROM workmanship_bop_bop_entries e
                JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid
                WHERE e.is_deleted = FALSE
                  {type_clause}
                  {like_clause}
                ORDER BY v.version_tag, e.sort_order
                LIMIT %s
                """,
                type_params + like_params + [limit],
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": rows}


@router.get("/entries/{gid}")
def get_entry(gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_ENTRY_BY_GID_SQL, (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="条目不存在")
    data = dict(row)
    data['process_flow_pic'] = _resolve_bop_pic_items(data.get('process_flow_pic') or [])
    return {"data": data}


@router.post("/entries", status_code=201)
def create_entry(body: CreateEntryBody, _u=Depends(_WRITE)):
    entry_gid  = str(next_gid())
    entity_gid = str(next_gid())
    link_gid   = str(next_gid())

    _ENTITY_TABLE_MAP = {
        'line_process':     ('workmanship_bop_bop_line',     'bop_line',    False, 'title'),
        'station_process':  ('workmanship_bop_bop_station',  'bop_station', False, 'title'),
        'process':          ('workmanship_bop_bop_process',  'bop_process', True,  'name'),
        'operation':        ('workmanship_bop_bop_steps',    'bop_steps',   True,  'title'),
        'operator_process': ('workmanship_bop_bop_operator', 'bop_operator', False, 'title'),
    }

    with get_conn() as conn:
        with conn.cursor() as cur:
            ver_gid = body.get_version_gid()
            _check_version_frozen(cur, ver_gid)
            if body.parent_gid:
                _check_line_editable(cur, ver_gid, body.parent_gid, _u)
            level   = _parent_level(cur, body.parent_gid)
            ai00_lv = _AI00_LEVEL.get(body.node_type)

            entity_info = _ENTITY_TABLE_MAP.get(body.node_type)

            if entity_info:
                e_table, link_type, has_vpps_desc, title_col = entity_info
                version_no = '01'
                ext_json = json.dumps({})
                params_json = json.dumps({})
                cur.execute("SELECT project_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (ver_gid,))
                ver_row = cur.fetchone()
                project_gid = ver_row['project_gid'] if ver_row else None
                if has_vpps_desc:
                    if body.node_type == 'process':
                        cur.execute(
                            f"INSERT INTO {e_table}(gid, project_gid, bop_version_gid, version_no, {title_col}, vpps, vpps_desc, vpps_part, part_feed, params, ext)"
                            f" VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (entity_gid, project_gid, ver_gid, version_no, body.title, body.vpps, body.vpps_desc, '', False, params_json, ext_json)
                        )
                    else:
                        cur.execute(
                            f"INSERT INTO {e_table}(gid, project_gid, version_no, {title_col}, vpps, vpps_desc, vpps_part, part_feed, params, ext)"
                            f" VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (entity_gid, project_gid, version_no, body.title, body.vpps, body.vpps_desc, '', False, params_json, ext_json)
                        )
                else:
                    if body.node_type == 'operator_process' and body.position:
                        ext_val = json.dumps({'position': body.position})
                        cur.execute(
                            f"INSERT INTO {e_table}(gid, project_gid, version_no, {title_col}, vpps, ext)"
                            f" VALUES (%s,%s,%s,%s,%s,%s)",
                            (entity_gid, project_gid, version_no, body.title, body.vpps, ext_val)
                        )
                    else:
                        if body.node_type == 'operation':
                            cur.execute(
                                f"INSERT INTO {e_table}(gid, project_gid, version_no, {title_col}, vpps, vpps_desc, vpps_part, part_feed, params, ext)"
                                f" VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                (entity_gid, project_gid, version_no, body.title, body.vpps, body.vpps_desc, '', False, params_json, ext_json)
                            )
                        else:
                            cur.execute(
                                f"INSERT INTO {e_table}(gid, project_gid, version_no, {title_col}, vpps, ext)"
                                f" VALUES (%s,%s,%s,%s,%s,%s)",
                                (entity_gid, project_gid, version_no, body.title, body.vpps, ext_json)
                            )
            else:
                link_type = None

            cur.execute(
                "INSERT INTO workmanship_bop_bop_entries"
                "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                " title, vpps, vpps_desc, vpps_part, part_feed, catia_occurrence_name,"
                " parent_vpps_name, parent_bop_title, child_vpps, meta, source_entry_gid)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'[]',%s,%s)",
                (entry_gid, ver_gid, body.parent_gid, body.node_type,
                 body.sort_order, level, ai00_lv,
                 body.title, body.vpps, body.vpps_desc, '', False, '', '',
                 body.parent_bop_title, json.dumps(body.meta or {}), None)
            )

            if entity_info:
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entry_links"
                    "(gid, version_gid, entry_gid, entity_gid, link_type, is_primary)"
                    " VALUES (%s,%s,%s,%s,%s,TRUE)",
                    (link_gid, ver_gid, entry_gid, entity_gid, link_type)
                )

            if body.parent_gid:
                _sync_child_vpps(cur, body.parent_gid, ver_gid)

            conn.commit()
            cur.execute(_ENTRY_BY_GID_SQL, (entry_gid,))
            row = cur.fetchone()
            entry_snapshot = dict(row) if row else {"gid": entry_gid, "title": body.title, "node_type": body.node_type, "parent_gid": body.parent_gid, "vpps": body.vpps}
            link_snapshot = {
                "gid": link_gid,
                "entry_gid": entry_gid,
                "version_gid": ver_gid,
                "link_type": link_type,
                "entity_gid": entity_gid,
                "is_primary": True,
            } if entity_info else None
            owned_snapshot = {"table": e_table, "gid": entity_gid, "title": body.title} if entity_info else None
            # ── 操作日志 ──
            batch_id, line_gid = _log_entry_op(cur,
                version_gid=ver_gid, entry_gid=entry_gid,
                entry_title=body.title or '',
                op_type='create_entry', old_state=None,
                new_state=_history.build_create_entry_snapshot(entry_snapshot, link_snapshot, owned_snapshot),
                user_gid=_u.get('gid', ''), user_name=_u.get('name', ''))
            conn.commit()  # 确保日志 INSERT 立即提交
            # 规则检验（WARN 模式，不阻断保存）
            try:
                from backend.platform_sdk.rules import check_entry_rules
                rule_warnings = check_entry_rules(body.node_type, entry_gid)
            except Exception:
                rule_warnings = []
            entry_data = dict(row) if row else {"gid": entry_gid, "entity_gid": entity_gid}
            entry_data['process_flow_pic'] = _resolve_bop_pic_items(entry_data.get('process_flow_pic') or [])
            resp = {
                "data": entry_data,
                "batch_id": batch_id,
                "line_gid": line_gid,
                "version_gid": ver_gid,
            }
            if rule_warnings:
                resp["rule_warnings"] = rule_warnings
            return resp


@router.patch("/entries/{gid}")
def update_entry(gid: str, body: UpdateEntryBody, _u=Depends(_WRITE)):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "无更新字段")

    _DIRECT_COLS = ('parent_gid', 'node_type', 'sort_order', 'title',
                    'vpps', 'vpps_desc', 'parent_bop_title')
    set_parts, vals = [], []
    for k in _DIRECT_COLS:
        if k in data:
            set_parts.append(f"{k}=%s")
            vals.append(data[k])
    if 'node_type' in data:
        set_parts.append("ai00_level=%s")
        vals.append(_AI00_LEVEL.get(data['node_type']))
    if 'process_flow_pic' in data:
        import json as _json
        set_parts.append("process_flow_pic=%s")
        vals.append(_json.dumps(_normalize_bop_pic_items(data['process_flow_pic'])))
    if 'meta' in data:
        import json as _json
        # 前端传来的 meta 是完整合并后的对象，整体覆盖 meta JSON 列
        set_parts.append("meta=CAST(%s AS JSON)")
        vals.append(_json.dumps(data['meta']))
    elif 'cad_sim_pics' in data:
        import json as _json
        set_parts.append("meta=JSON_SET(IFNULL(meta,'{}'),'$.cad_sim_pics',CAST(%s AS JSON))")
        vals.append(_json.dumps(data['cad_sim_pics']))
    set_parts.append("updated_at=NOW()")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT e.version_gid, e.title, e.node_type, v.project_gid,"
                " e.parent_gid, e.sort_order, e.vpps, e.vpps_desc, e.parent_bop_title,"
                " COALESCE(e.process_flow_pic, '[]') AS process_flow_pic,"
                " COALESCE(JSON_EXTRACT(e.meta, '$.cad_sim_pics'), JSON_ARRAY()) AS cad_sim_pics "
                "FROM workmanship_bop_bop_entries e "
                "JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid "
                "WHERE e.gid = %s",
                (gid,)
            )
            entry_row = cur.fetchone()
            if entry_row:
                _check_version_frozen(cur, entry_row['version_gid'])
                _check_line_editable(cur, entry_row['version_gid'], gid, _u)
            cur.execute(
                f"UPDATE workmanship_bop_bop_entries SET {', '.join(set_parts)} WHERE gid=%s",
                vals + [gid]
            )
            if cur.rowcount == 0: _not_found(gid)
            if 'title' in data:
                cur.execute(
                    "SELECT entity_gid, link_type FROM workmanship_bop_bop_entry_links "
                    "WHERE entry_gid=%s AND is_primary=TRUE LIMIT 1",
                    (gid,)
                )
                lnk = cur.fetchone()
                if lnk:
                    _ENTITY_SYNC = {
                        'bop_line':     ('workmanship_bop_bop_line',     'title'),
                        'bop_station':  ('workmanship_bop_bop_station',  'title'),
                        'bop_process':  ('workmanship_bop_bop_process',  'name'),
                        'bop_steps':    ('workmanship_bop_bop_steps',    'title'),
                        'bop_operator': ('workmanship_bop_bop_operator', 'title'),
                    }
                    sync = _ENTITY_SYNC.get(lnk['link_type'])
                    if sync:
                        t, col = sync
                        try:
                            cur.execute(f"UPDATE {t} SET {col}=%s WHERE gid=%s",
                                        (data['title'], lnk['entity_gid']))
                        except Exception as _e:
                            _log.warning("entity title sync skipped for gid=%s link_type=%s: %s",
                                         gid, lnk['link_type'], _e)
            conn.commit()
            # ── 操作日志 ──
            batch_ids = []
            line_gid = None
            if entry_row:
                for event in _history.build_entry_log_events(dict(entry_row), data):
                    batch_id, lg = _log_entry_op(cur,
                        version_gid=entry_row['version_gid'],
                        entry_gid=gid, entry_title=(data.get('title') or entry_row['title'] or ''),
                        op_type=event['op_type'],
                        old_state=event['old_state'], new_state=event['new_state'],
                        user_gid=_u.get('gid', ''), user_name=_u.get('name', ''))
                    batch_ids.append(batch_id)
                    line_gid = lg
                conn.commit()  # 确保日志 INSERT 立即提交
            cur.execute(_ENTRY_BY_GID_SQL, (gid,))
            row = cur.fetchone()
            data = dict(row) if row else {}
            data['process_flow_pic'] = _resolve_bop_pic_items(data.get('process_flow_pic') or [])
            data['process_chart_pic'] = _resolve_bop_pic_items(data.get('process_chart_pic') or [])
            return {
                "data": data,
                "batch_ids": batch_ids,
                "line_gid": line_gid,
                "version_gid": entry_row['version_gid'] if entry_row else None,
            }


@router.post("/pics/upload")
def upload_bop_pic(body: BopPicUploadBody, _u=Depends(_WRITE)):
    _log.info(
        "bop pic upload request filename=%s mime=%s b64_len=%s",
        body.filename,
        body.mime,
        len(body.data_b64 or ""),
    )
    if not body.mime.startswith("image/"):
        raise HTTPException(400, "只允许上传图片文件")
    try:
        data = _b64.b64decode(body.data_b64, validate=True)
    except Exception:
        raise HTTPException(400, "base64 数据格式无效")
    from pathlib import Path as _Path
    ext = _Path(body.filename).suffix.lower() or {
        "image/jpeg": ".jpg", "image/png": ".png",
        "image/gif": ".gif", "image/webp": ".webp",
    }.get(body.mime, ".jpg")
    _log.info(
        "bop pic upload decoded filename=%s bytes=%s ext=%s",
        body.filename,
        len(data),
        ext,
    )
    if len(data) > _BOP_PICS_MAX:
        raise HTTPException(400, f"图片大小超过 5MB 限制")
    from backend.platform_sdk import blob_storage as _storage
    minio_url = _storage.upload(data, ext, body.mime, prefix="bop_pics")
    _log.info(
        "bop pic upload storage result filename=%s url=%s",
        body.filename,
        minio_url,
    )
    if minio_url:
        payload = {"url": minio_url}
        from backend.platform_sdk import ois_storage as _ois_storage
        ois_cfg = _ois_storage._get_ois_config()
        public_base = str(ois_cfg.get('public_base_url') or '').rstrip('/')
        identify = str(ois_cfg.get('identify') or '').strip()
        if identify:
            if public_base and minio_url.startswith(public_base + '/'):
                payload['storage'] = 'ois'
                payload['object_key'] = minio_url[len(public_base) + 1:]
            elif not public_base and 'authorization=' in minio_url:
                try:
                    object_key = minio_url.split('://', 1)[1].split('/', 2)[2].split('?', 1)[0]
                    payload['storage'] = 'ois'
                    payload['object_key'] = object_key
                except Exception:
                    pass
        return payload
    _BOP_PICS_DIR.mkdir(parents=True, exist_ok=True)
    name = _uuid.uuid4().hex + ext
    (_BOP_PICS_DIR / name).write_bytes(data)
    _log.warning(
        "bop pic upload fallback to local filename=%s saved_name=%s",
        body.filename,
        name,
    )
    return {"url": f"/static/uploads/bop_pics/{name}"}

@router.delete("/entries/{gid}", status_code=200)
def delete_entry(gid: str, _u=Depends(_WRITE)):
    # 自有实体类型（1:1 归属 entry，随 entry 一起软删除）
    _OWNED_ENTITY_TYPES = {'bop_line', 'bop_station', 'bop_process', 'bop_steps', 'bop_operator'}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version_gid, parent_gid, title, node_type, vpps "
                "FROM workmanship_bop_bop_entries WHERE gid=%s",
                (gid,)
            )
            entry_row = cur.fetchone()
            if entry_row:
                _check_version_frozen(cur, entry_row['version_gid'])
                _check_line_editable(cur, entry_row['version_gid'], gid, _u)

            # 软删除 entry 本身
            cur.execute(
                "UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW() WHERE gid=%s",
                (gid,)
            )
            if cur.rowcount == 0: _not_found(gid)

            # 查询所有 links（含 entity_gid 和 link_type）
            cur.execute(
                "SELECT entity_gid, link_type FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND deleted_at IS NULL",
                (gid,)
            )
            links = cur.fetchall()

            # 对自有实体做软删除
            for lk in links:
                lt = lk['link_type']
                if lt not in _OWNED_ENTITY_TYPES:
                    continue
                table_info = _LINK_TARGET_TABLES.get(lt)
                if not table_info:
                    continue
                table_name, gid_col, _ = table_info
                cur.execute(
                    f"UPDATE {table_name} SET deleted_at=NOW() WHERE {gid_col}=%s AND deleted_at IS NULL",
                    (lk['entity_gid'],)
                )

            # 软删除所有 bop_entry_links
            cur.execute(
                "UPDATE workmanship_bop_bop_entry_links SET deleted_at=NOW() WHERE entry_gid=%s AND deleted_at IS NULL",
                (gid,)
            )

            if entry_row and entry_row['parent_gid']:
                _sync_child_vpps(cur, entry_row['parent_gid'], entry_row['version_gid'])
            conn.commit()
            link_snapshots = [
                {
                    "gid": f"link-{idx}",
                    "entry_gid": gid,
                    "version_gid": entry_row['version_gid'],
                    "link_type": lk['link_type'],
                    "entity_gid": lk['entity_gid'],
                    "is_primary": True,
                }
                for idx, lk in enumerate(links, start=1)
            ]
            owned_snapshots = [
                {"table": _LINK_TARGET_TABLES[lk['link_type']][0], "gid": lk['entity_gid'], "title": entry_row.get('title')}
                for lk in links if lk['link_type'] in _OWNED_ENTITY_TYPES and _LINK_TARGET_TABLES.get(lk['link_type'])
            ]
            # ── 操作日志 ──
            if entry_row:
                batch_id, line_gid = _log_entry_op(cur,
                    version_gid=entry_row['version_gid'],
                    entry_gid=gid, entry_title=entry_row.get('title') or '',
                    op_type='delete_entry', new_state=None,
                    old_state=_history.build_delete_entry_snapshot(dict(entry_row), link_snapshots, owned_snapshots),
                    user_gid=_u.get('gid', ''), user_name=_u.get('name', ''))
                conn.commit()  # 确保日志 INSERT 立即提交
                return {
                    "deleted": True,
                    "gid": gid,
                    "batch_id": batch_id,
                    "line_gid": line_gid,
                    "version_gid": entry_row['version_gid'],
                }
            return {"deleted": True, "gid": gid}


class PurgeEntriesBody(BaseModel):
    mode: Literal['soft', 'hard'] = 'soft'


@router.post("/versions/{version_gid}/purge-entries", status_code=200)
def purge_version_entries(version_gid: str, body: PurgeEntriesBody,
                          _u=Depends(_SUPER_ADMIN)):
    """
    超管：按版本批量清空全部条目及其私有实体记录。
    mode=soft  → is_deleted=TRUE / deleted_at=NOW()（可通过 DB 恢复）
    mode=hard  → DELETE FROM（永久不可恢复）
    私有实体 = _DEEP_COPY_ENTITY_TABLES 中列出的 12 种 link_type 所指向的实体表。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
            if not cur.fetchone():
                raise HTTPException(404, f"版本 {version_gid} 不存在")

            counts: dict = {'entities': {}, 'links': 0, 'entries': 0}

            # ── 1. 清除私有实体（_DEEP_COPY_ENTITY_TABLES 中的 12 种类型）─────
            for link_type, (table, _file_cols) in _DEEP_COPY_ENTITY_TABLES.items():
                if body.mode == 'hard':
                    cur.execute(
                        f"DELETE FROM {table} WHERE gid IN ("
                        f"  SELECT entity_gid FROM workmanship_bop_bop_entry_links"
                        f"  WHERE version_gid=%s AND link_type=%s"
                        f")",
                        (version_gid, link_type),
                    )
                else:
                    cur.execute(
                        f"UPDATE {table} SET deleted_at=NOW()"
                        f" WHERE gid IN ("
                        f"  SELECT entity_gid FROM workmanship_bop_bop_entry_links"
                        f"  WHERE version_gid=%s AND link_type=%s"
                        f") AND deleted_at IS NULL",
                        (version_gid, link_type),
                    )
                n = cur.rowcount
                if n:
                    counts['entities'][link_type] = n

            # ── 2. 清除 bop_entry_links ───────────────────────────────────────
            if body.mode == 'hard':
                cur.execute(
                    "DELETE FROM workmanship_bop_bop_entry_links WHERE version_gid=%s",
                    (version_gid,),
                )
            else:
                cur.execute(
                    "UPDATE workmanship_bop_bop_entry_links SET deleted_at=NOW()"
                    " WHERE version_gid=%s AND deleted_at IS NULL",
                    (version_gid,),
                )
            counts['links'] = cur.rowcount

            # ── 3. 清除 bop_entries ───────────────────────────────────────────
            if body.mode == 'hard':
                cur.execute(
                    "DELETE FROM workmanship_bop_bop_entries WHERE version_gid=%s",
                    (version_gid,),
                )
            else:
                cur.execute(
                    "UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW()"
                    " WHERE version_gid=%s AND is_deleted=FALSE",
                    (version_gid,),
                )
            counts['entries'] = cur.rowcount

            conn.commit()
            return {"ok": True, "mode": body.mode,
                    "version_gid": version_gid, "counts": counts}


@router.post("/versions/{version_gid}/import-tc", status_code=201)
def import_tc_entries(version_gid: str, body: ImportTcBody, _u=Depends(_WRITE)):
    """批量导入 TC CSV 解析结果"""
    _IMPORT_ENTITY_MAP = {
        'line_process':     ('workmanship_bop_bop_line',       'bop_line'),
        'station_process':  ('workmanship_bop_bop_station',    'bop_station'),
        'process':          ('workmanship_bop_bop_process',    'bop_process'),
        'operation':        ('workmanship_bop_bop_steps',      'bop_steps'),
        'operator_process': ('workmanship_bop_bop_operator',   'bop_operator'),
        # 项目资源需求节点
        'equipment_need':   ('workmanship_bop_bop_equipments', 'project_equipment'),
        'fixture_need':     ('workmanship_bop_bop_fixtures',   'project_tooling'),
        'tool_need':        ('workmanship_bop_bop_tools',      'project_tools'),
        # TC 零件既保留为树节点，也写入 PBOM 实体表，通过 pbom_part 显示为“装配零件”
        'part':              ('workmanship_bop_pbom',           'pbom_part'),
        'non_standard_part': ('workmanship_bop_pbom',           'pbom_part'),
        'standard_part':     ('workmanship_bop_pbom',           'pbom_part'),
        'support_material':  ('workmanship_bop_pbom',           'pbom_part'),
    }

    try:
        rows = body.rows
        _log.info("[import-tc] version=%s rows=%d", version_gid, len(rows))
        if not rows:
            return {"data": [], "count": 0}

        # ── 过滤：node_type 无法识别的行跳过（前端已过滤，此处兜底）
        rows = [
            r for r in rows
            if r.get('ai00_level') is not None or _AI00_LEVEL.get(r.get('node_type', '')) is not None
        ]
        if not rows:
            return {"data": [], "count": 0, "skipped": "all rows had unknown node_type"}

        def _safe_int(v, default=0):
            try: return int(v)
            except (TypeError, ValueError): return default

        def _safe_float(v, default=1.0):
            try: return float(v)
            except (TypeError, ValueError): return default

        rows = sorted(rows, key=lambda r: _safe_int(r.get('_level', 0)))

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT project_gid, frozen_at, pbom_version_gid, bop_name"
                            " FROM workmanship_bop_bop_versions WHERE gid=%s",
                            (version_gid,))
                ver = cur.fetchone()
                if not ver:
                    raise HTTPException(404, f"版本 {version_gid} 不存在")
                if ver['frozen_at']:
                    raise HTTPException(403, "版本已冻结，不允许导入")
                project_gid = ver['project_gid']
                pbom_version_gid = ver.get('pbom_version_gid')

                # PBOM 零件实体必须归属一个 PBOM 版本。TC 导入含零件且 BOP 尚未绑定
                # PBOM 时，自动创建一个专用于本次导入的版本并回写绑定。
                has_part_rows = any(r.get('node_type') in _PART_NODE_TYPES for r in rows)
                if has_part_rows and not pbom_version_gid:
                    pbom_version_gid = str(next_gid())
                    pbom_name = f"{ver.get('bop_name') or 'BOP'} - TC导入零件"
                    cur.execute(
                        "INSERT INTO workmanship_bop_pbom_versions"
                        " (gid, project_gid, version_tag, name, source_type, status, meta,"
                        " visibility, shared_team_gid, shared_project_gid)"
                        " VALUES (%s,%s,%s,%s,'tc','draft',%s,'project',NULL,NULL)",
                        (pbom_version_gid, project_gid, 'TC导入', pbom_name,
                         json.dumps({'source_bop_version_gid': version_gid}, ensure_ascii=False)),
                    )
                    cur.execute(
                        "UPDATE workmanship_bop_bop_versions SET pbom_version_gid=%s WHERE gid=%s",
                        (pbom_version_gid, version_gid),
                    )

                # ── TC 同步：下线上一次 TC 导入生成的数据 ──────────────────
                # 仅处理带 import_source=tc 标记的数据，不影响手工或其他来源节点。
                cur.execute(
                    "SELECT gid FROM workmanship_bop_bop_entries"
                    " WHERE version_gid=%s AND is_deleted=FALSE"
                    " AND JSON_UNQUOTE(JSON_EXTRACT(meta, '$.import_source'))='tc'",
                    (version_gid,),
                )
                previous_tc_entry_gids = [r['gid'] for r in cur.fetchall()]
                replaced = len(previous_tc_entry_gids)
                if previous_tc_entry_gids:
                    placeholders = ','.join(['%s'] * len(previous_tc_entry_gids))
                    cur.execute(
                        f"SELECT entity_gid, link_type FROM workmanship_bop_bop_entry_links"
                        f" WHERE entry_gid IN ({placeholders}) AND deleted_at IS NULL",
                        previous_tc_entry_gids,
                    )
                    previous_tc_links = [dict(r) for r in cur.fetchall()]

                    # TC 自建的资源实体和 PBOM 实体随本批数据一起下线。
                    tc_entity_tables = {
                        'project_equipment': 'workmanship_bop_bop_equipments',
                        'project_tooling': 'workmanship_bop_bop_fixtures',
                        'project_tools': 'workmanship_bop_bop_tools',
                    }
                    for link_type, table_name in tc_entity_tables.items():
                        entity_gids_for_type = [
                            link['entity_gid'] for link in previous_tc_links
                            if link['link_type'] == link_type
                        ]
                        if entity_gids_for_type:
                            entity_placeholders = ','.join(['%s'] * len(entity_gids_for_type))
                            cur.execute(
                                f"UPDATE {table_name} SET is_deleted=TRUE, deleted_at=NOW()"
                                f" WHERE gid IN ({entity_placeholders}) AND is_deleted=FALSE",
                                entity_gids_for_type,
                            )

                    previous_part_gids = [
                        link['entity_gid'] for link in previous_tc_links
                        if link['link_type'] == 'pbom_part'
                    ]
                    if previous_part_gids:
                        part_placeholders = ','.join(['%s'] * len(previous_part_gids))
                        cur.execute(
                            f"UPDATE workmanship_bop_pbom SET is_deleted=TRUE"
                            f" WHERE gid IN ({part_placeholders}) AND is_deleted=FALSE",
                            previous_part_gids,
                        )

                    cur.execute(
                        f"UPDATE workmanship_bop_bop_entry_links SET deleted_at=NOW()"
                        f" WHERE entry_gid IN ({placeholders}) AND deleted_at IS NULL",
                        previous_tc_entry_gids,
                    )
                    cur.execute(
                        f"UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW()"
                        f" WHERE gid IN ({placeholders}) AND is_deleted=FALSE",
                        previous_tc_entry_gids,
                    )

                # ── 重复检测：加载该版本已有条目的字段指纹 ─────────────────
                cur.execute(
                    "SELECT node_type, title, vpps, vpps_desc, parent_bop_title"
                    " FROM workmanship_bop_bop_entries"
                    " WHERE version_gid=%s AND is_deleted=FALSE",
                    (version_gid,)
                )
                def _fp(node_type, title, vpps, vpps_desc, parent_bop_title):
                    return (
                        node_type or '',
                        title or '',
                        vpps or '',
                        vpps_desc or '',
                        parent_bop_title or '',
                    )
                existing_fps = {
                    _fp(e['node_type'], e['title'], e['vpps'], e['vpps_desc'], e['parent_bop_title'])
                    for e in cur.fetchall()
                }

                # 过滤掉已存在的行
                new_rows = [
                    r for r in rows
                    if _fp(
                        r.get('node_type', ''),
                        r.get('title', ''),
                        r.get('vpps') or '',
                        r.get('vpps_desc') or '',
                        r.get('parent_bop_label') or r.get('parent_label') or '',
                    ) not in existing_fps
                ]
                skipped = len(rows) - len(new_rows)
                if not new_rows:
                    raise HTTPException(409, f"所有 {len(rows)} 行均已存在于该版本，跳过导入")
                rows = new_rows
                # ─────────────────────────────────────────────────────────────

                entry_gids  = [str(next_gid()) for _ in rows]
                entity_gids = [str(next_gid()) for _ in rows]
                link_gids   = [str(next_gid()) for _ in rows]
                label_to_gid: dict = {}
                part_label_to_entity_gid: dict = {}
                for i, r in enumerate(rows):
                    lbl = r.get('bom_row_label') or r.get('label') or ''
                    if lbl:
                        label_to_gid[lbl] = entry_gids[i]
                        if r.get('node_type') in _PART_NODE_TYPES:
                            part_label_to_entity_gid[lbl] = entity_gids[i]
                        # 同时注册 "/" 前的短 ID（TC 格式：AS-000499138/00;1-...）
                        short = lbl.split('/')[0].strip()
                        if short and short != lbl:
                            label_to_gid.setdefault(short, entry_gids[i])
                            if r.get('node_type') in _PART_NODE_TYPES:
                                part_label_to_entity_gid.setdefault(short, entity_gids[i])

                # ── 收集数据，批量 INSERT ─────────────────────────────────
                entry_rows = []
                link_rows = []
                parent_gids_to_sync = set()
                created = []

                for i, r in enumerate(rows):
                    e_gid        = entry_gids[i]
                    ent_gid      = entity_gids[i]
                    lnk_gid      = link_gids[i]
                    node_type    = r.get('node_type', '')
                    lv           = _safe_int(r.get('_level', 0))
                    ai00_lv      = r.get('ai00_level') if r.get('ai00_level') is not None else _AI00_LEVEL.get(node_type)
                    title        = r.get('title', '')
                    vpps         = r.get('vpps') or None
                    vpps_desc    = r.get('vpps_desc') or None
                    parent_label = r.get('parent_bop_label') or r.get('parent_label') or None
                    if parent_label:
                        parent_gid = (label_to_gid.get(parent_label)
                                      or label_to_gid.get(parent_label.split('/')[0].strip()))
                    else:
                        parent_gid = None

                    entity_info = _IMPORT_ENTITY_MAP.get(node_type)

                    # entity 表逐行 INSERT IGNORE（各实体表结构不同，不能批量）
                    if entity_info:
                        e_table, link_type = entity_info
                        if node_type == 'operation':
                            cur.execute(
                                "INSERT IGNORE INTO workmanship_bop_bop_steps "
                                "(gid, project_gid, title, vpps, vpps_desc,"
                                " operation_code, vpps_part, part_feed, version_no, params, ext,"
                                " is_deleted, is_archived)"
                                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'01',JSON_OBJECT(),JSON_OBJECT(),FALSE,FALSE)",
                                (ent_gid, project_gid, title, vpps, vpps_desc,
                                 r.get('operation_code', ''),
                                 r.get('vpps_part', ''), r.get('part_feed', False))
                            )
                        elif node_type == 'operator_process':
                            cur.execute(
                                "INSERT IGNORE INTO workmanship_bop_bop_operator "
                                "(gid, project_gid, title, vpps, role_type,"
                                " factory_role_ref_gid, headcount, version_no, ext,"
                                " is_deleted, is_archived)"
                                " VALUES (%s,%s,%s,%s,%s,%s,%s,'01',JSON_OBJECT(),FALSE,FALSE)",
                                (ent_gid, project_gid, title, vpps,
                                 r.get('role_type', ''),
                                 r.get('factory_role_ref_gid') or None,
                                 r.get('headcount', 1))
                            )
                        elif node_type == 'process':
                            cur.execute(
                                "INSERT IGNORE INTO workmanship_bop_bop_process"
                                "(gid, project_gid, bop_version_gid, name, vpps, vpps_desc,"
                                " version_no, vpps_part, part_feed, params, ext, is_deleted, is_archived)"
                                " VALUES (%s,%s,%s,%s,%s,%s,'01','',FALSE,JSON_OBJECT(),JSON_OBJECT(),FALSE,FALSE)",
                                (ent_gid, project_gid, version_gid, title, vpps, vpps_desc)
                            )
                        elif node_type in ('equipment_need', 'fixture_need', 'tool_need'):
                            cur.execute(
                                f"INSERT IGNORE INTO {e_table}"
                                f" (gid, project_gid, title, vpps, version_no, quantity, status,"
                                f" ext, is_deleted, is_archived)"
                                f" VALUES (%s,%s,%s,%s,'01',1,'pending',JSON_OBJECT(),FALSE,FALSE)",
                                (ent_gid, project_gid, title, vpps)
                            )
                        elif node_type in _PART_NODE_TYPES:
                            parent_part_gid = None
                            if parent_label:
                                parent_part_gid = (
                                    part_label_to_entity_gid.get(parent_label)
                                    or part_label_to_entity_gid.get(parent_label.split('/')[0].strip())
                                )
                            part_vpps = r.get('vpps_part') or vpps
                            cur.execute(
                                "INSERT IGNORE INTO workmanship_bop_pbom"
                                " (gid, snapshot_gid, part_no, title, quantity, parent_gid,"
                                " vpps, vpps_desc, parent_vpps, parent_vpps_name,"
                                " bom_row, bom_row_label, component_id, component_type,"
                                " torque, torque_importance, ownership_user, level,"
                                " catia_occurrence_name, unit, vpps_source, is_deleted, meta)"
                                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pcs','tc',FALSE,%s)",
                                (ent_gid, pbom_version_gid,
                                 r.get('bom_row_id') or r.get('bom_row_label') or title,
                                 title, _safe_float(r.get('quantity')), parent_part_gid,
                                 part_vpps, vpps_desc or '', r.get('parent_vpps') or '',
                                 r.get('parent_vpps_name') or '', r.get('bom_row_label') or '',
                                 r.get('bom_row_label') or '', r.get('bom_row_id') or '',
                                 node_type, r.get('torque') or '',
                                 r.get('torque_importance') or '', r.get('bom_row_owner') or '',
                                 lv, r.get('catia_occurrence_name') or '',
                                 json.dumps({'tc_node_type': node_type}, ensure_ascii=False))
                            )
                        else:
                            cur.execute(
                                f"INSERT IGNORE INTO {e_table}"
                                f" (gid, project_gid, title, vpps, version_no, ext, is_deleted, is_archived)"
                                f" VALUES (%s,%s,%s,%s,'01',JSON_OBJECT(),FALSE,FALSE)",
                                (ent_gid, project_gid, title, vpps)
                            )
                    else:
                        link_type = None

                    sort_val = r.get('seq_no', r.get('sort_order', i))
                    entry_rows.append((
                        e_gid, version_gid, parent_gid, node_type,
                        sort_val, lv, ai00_lv,
                        title, vpps, vpps_desc,
                        '', False, '', '',
                        parent_label,
                        json.dumps({
                            'import_source': 'tc',
                            'tc_key': r.get('bom_row_id') or r.get('bom_row_label') or '',
                        }, ensure_ascii=False),
                    ))

                    if entity_info:
                        link_rows.append((
                            lnk_gid, version_gid, e_gid, ent_gid, link_type,
                        ))

                    if parent_gid:
                        parent_gids_to_sync.add(parent_gid)
                    created.append(e_gid)

                # ── 批量写入 entries 和 links ────────────────────────────
                if entry_rows:
                    cur.executemany(
                        "INSERT INTO workmanship_bop_bop_entries"
                        "(gid, version_gid, parent_gid, node_type,"
                        " sort_order, level, ai00_level,"
                        " title, vpps, vpps_desc, vpps_part, part_feed, catia_occurrence_name, parent_vpps_name,"
                        " parent_bop_title, child_vpps, meta, is_deleted, is_archived)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'[]',%s,FALSE,FALSE)",
                        entry_rows,
                    )
                if link_rows:
                    cur.executemany(
                        "INSERT INTO workmanship_bop_bop_entry_links"
                        "(gid, version_gid, entry_gid, entity_gid, link_type, is_primary,"
                        " is_inherited, is_deleted, is_archived)"
                        " VALUES (%s,%s,%s,%s,%s,TRUE,FALSE,FALSE,FALSE)",
                        link_rows,
                    )

                # ── 同步 child_vpps ──────────────────────────────────────
                for pg in parent_gids_to_sync:
                    _sync_child_vpps(cur, pg, version_gid)

                conn.commit()
                _log.info("[import-tc] committed %d rows", len(created))
                return {"count": len(created), "skipped": skipped, "replaced": replaced}

    except HTTPException:
        raise
    except Exception as e:
        _log.error("[import-tc] UNHANDLED ERROR: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"import-tc failed: {e}")


@router.post("/versions/{version_gid}/copy-from/{src_gid}", status_code=201)
def copy_entries_from(version_gid: str, src_gid: str, _u=Depends(_WRITE)):
    """从另一 BOP 版本复制全部条目"""
    return _do_copy(version_gid, src_gid, set_gbop_source=False)


@router.post("/versions/{version_gid}/copy-from-gbop/{src_gid}", status_code=201)
def copy_entries_from_gbop(version_gid: str, src_gid: str, _u=Depends(_WRITE)):
    """从 GBOP 版本导入全部条目，并记录 gbop_source_gid 溯源"""
    return _do_copy(version_gid, src_gid, set_gbop_source=True)


# ══════════════════════════════════════════════════════════════
# Auto-Link
# ══════════════════════════════════════════════════════════════

@router.get("/versions/{version_gid}/auto-link-preview")
def auto_link_preview(version_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT project_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, f"版本 {version_gid} 不存在")

            need_types = list(_PROCESS_ENTITY_MAP.keys()) + list(_PART_NODE_TYPES)
            placeholders = ','.join(['%s'] * len(need_types))
            cur.execute(
                f"SELECT e.gid, e.node_type, e.title, e.vpps, e.vpps_desc, e.sort_order "
                f"FROM workmanship_bop_bop_entries e "
                f"WHERE e.version_gid=%s AND e.is_deleted = FALSE "
                f"  AND e.node_type IN ({placeholders}) "
                f"ORDER BY e.sort_order",
                [version_gid] + need_types,
            )
            entries = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT entry_gid FROM workmanship_bop_bop_entry_links "
                "WHERE entry_gid IN ("
                f"  SELECT gid FROM workmanship_bop_bop_entries WHERE version_gid=%s"
                ") AND is_primary=TRUE",
                (version_gid,),
            )
            already_linked = {r['entry_gid'] for r in cur.fetchall()}

            items = []
            for e in entries:
                nt = e['node_type']
                item = {
                    'entry_gid':    e['gid'],
                    'node_type':    nt,
                    'title':        e['title'] or '',
                    'vpps':         e.get('vpps') or '',
                    'sort_order':   e['sort_order'],
                    'status':       'skip' if e['gid'] in already_linked else 'pending',
                    'message':      '已有关联' if e['gid'] in already_linked else '',
                }
                if item['status'] != 'skip':
                    if nt in _PROCESS_ENTITY_MAP:
                        item['action'] = '建 stub 实体 → link'
                        item['step'] = 'A'
                    elif nt in _PART_NODE_TYPES:
                        if not e.get('bom_row_id'):
                            item['status'] = 'warn'
                            item['message'] = 'bom_row_id 为空，无法匹配'
                        else:
                            item['action'] = '按 bom_row_id 匹配零件'
                            item['step'] = 'B'
                items.append(item)

            return {"data": {
                "version_gid": version_gid,
                "total": len(items),
                "pending": sum(1 for i in items if i['status'] == 'pending'),
                "skip": sum(1 for i in items if i['status'] == 'skip'),
                "warn": sum(1 for i in items if i['status'] == 'warn'),
                "items": items,
            }}


@router.post("/versions/{version_gid}/auto-link", status_code=200)
def auto_link_entries(version_gid: str, body: AutoLinkBody = AutoLinkBody(), _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT project_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, f"版本 {version_gid} 不存在")
            project_gid = ver['project_gid']

            step = body.step
            mode = body.mode if body.mode in ('incremental', 'repair') else 'incremental'

            need_types = []
            if step in ('A', 'all'):
                need_types.extend(_PROCESS_ENTITY_MAP.keys())
            if step in ('B', 'all'):
                need_types.extend(_PART_NODE_TYPES)

            if not need_types:
                raise HTTPException(400, "step 无效，可选: A / B / all")

            placeholders = ','.join(['%s'] * len(need_types))
            cur.execute(
                f"SELECT e.gid, e.node_type, e.title, e.vpps, e.vpps_desc, e.sort_order "
                f"FROM workmanship_bop_bop_entries e "
                f"WHERE e.version_gid=%s AND e.is_deleted = FALSE "
                f"  AND e.node_type IN ({placeholders}) "
                f"ORDER BY e.sort_order",
                [version_gid] + need_types,
            )
            entries = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT entry_gid FROM workmanship_bop_bop_entry_links "
                "WHERE entry_gid IN ("
                f"  SELECT gid FROM workmanship_bop_bop_entries WHERE version_gid=%s"
                ") AND is_primary=TRUE",
                (version_gid,),
            )
            already_linked = {r['entry_gid'] for r in cur.fetchall()}

            results = []

            for e in entries:
                nt = e['node_type']
                entry_result = {
                    'entry_gid':   e['gid'],
                    'node_type':   nt,
                    'title':       e['title'] or '',
                    'vpps':        e.get('vpps') or '',
                    'sort_order':  e['sort_order'],
                    'status':      'ok',
                    'link_action': 'created',
                    'message':     '',
                    'rule_results': _check_auto_link_rules(cur, e, version_gid),
                }

                if mode == 'repair' and e['gid'] in already_linked:
                    cur.execute(
                        "SELECT l.gid AS link_gid, l.link_type, l.entity_gid "
                        "FROM workmanship_bop_bop_entry_links l "
                        "WHERE l.entry_gid = %s AND l.is_primary = TRUE",
                        (e['gid'],),
                    )
                    existing_links = cur.fetchall()
                    stale_count = 0
                    for lk in existing_links:
                        target_table = _LINK_TARGET_TABLE.get(lk['link_type'])
                        if target_table:
                            cur.execute(f"SELECT 1 FROM {target_table} WHERE gid = %s", (lk['entity_gid'],))
                            if not cur.fetchone():
                                cur.execute(
                                    "DELETE FROM workmanship_bop_bop_entry_links WHERE gid = %s",
                                    (lk['link_gid'],),
                                )
                                stale_count += 1
                    if stale_count > 0:
                        already_linked.discard(e['gid'])
                        entry_result['link_action'] = 'repaired'
                        entry_result['message'] = f'已清理 {stale_count} 条 stale link，重新匹配'
                    else:
                        entry_result['status'] = 'skip'
                        entry_result['link_action'] = 'skipped'
                        entry_result['message'] = '关联有效，无需修复'
                        results.append(entry_result)
                        continue

                elif e['gid'] in already_linked:
                    entry_result['status'] = 'skip'
                    entry_result['link_action'] = 'skipped'
                    entry_result['message'] = '已有 is_primary 关联'
                    results.append(entry_result)
                    continue

                try:
                    if nt in _PROCESS_ENTITY_MAP and step in ('A', 'all'):
                        table, link_type = _PROCESS_ENTITY_MAP[nt]
                        entry_vpps = e.get('vpps') or ''

                        matched_entity = None
                        if entry_vpps:
                            cur.execute(
                                f"SELECT gid, title FROM {table} WHERE vpps = %s",
                                (entry_vpps,),
                            )
                            matches = cur.fetchall()
                            if len(matches) == 1:
                                matched_entity = matches[0]
                            elif len(matches) > 1:
                                entry_result['status'] = 'warn'
                                entry_result['link_action'] = 'warn'
                                entry_result['message'] = (
                                    f'vpps={entry_vpps} 在 {table} 中匹配到 {len(matches)} 条，需手动选择'
                                )
                                results.append(entry_result)
                                continue

                        if matched_entity:
                            entity_gid = matched_entity['gid']
                            entry_result['link_action'] = 'matched'
                            entry_result['message'] = f'匹配已有实体 {entity_gid[:8]}…'
                        else:
                            entity_gid = str(next_gid())
                            title = e['title'] or '（未命名）'
                            # bop_process 用 name 列且需要 bop_version_gid
                            if table == 'workmanship_bop_bop_process':
                                cur.execute(
                                    f"INSERT INTO {table} "
                                    f"(gid, project_gid, bop_version_gid, name, vpps)"
                                    f" VALUES (%s,%s,%s,%s,%s)",
                                    (entity_gid, project_gid, version_gid, title, entry_vpps or None),
                                )
                            else:
                                cur.execute(
                                    f"INSERT INTO {table} "
                                    f"(gid, project_gid, title, vpps) VALUES (%s,%s,%s,%s)",
                                    (entity_gid, project_gid, title, entry_vpps or None),
                                )
                            entry_result['link_action'] = 'created'
                            entry_result['message'] = f'新建 stub 实体 {entity_gid[:8]}…'

                        cur.execute(
                            "INSERT INTO workmanship_bop_bop_entry_links "
                            "(gid, version_gid, entry_gid, entity_gid, link_type, is_primary) "
                            "VALUES (%s,%s,%s,%s,%s,TRUE) "
                            "",
                            (str(next_gid()), version_gid, e['gid'], entity_gid, link_type),
                        )

                    elif nt in _PART_NODE_TYPES and step in ('B', 'all'):
                        entry_vpps = e.get('vpps') or ''
                        if not entry_vpps:
                            entry_result['status'] = 'warn'
                            entry_result['link_action'] = 'warn'
                            entry_result['message'] = 'vpps 为空，无法匹配'
                        else:
                            cur.execute(
                                "SELECT gid, title, part_no FROM workmanship_bop_pbom WHERE vpps = %s",
                                (entry_vpps,),
                            )
                            matches = cur.fetchall()
                            if len(matches) == 1:
                                part = matches[0]
                                cur.execute(
                                    "INSERT INTO workmanship_bop_bop_entry_links "
                                    "(gid, version_gid, entry_gid, entity_gid, link_type, is_primary) "
                                    "VALUES (%s,%s,%s,%s,'pbom_part',TRUE) "
                                    "",
                                    (str(next_gid()), version_gid, e['gid'], part['gid']),
                                )
                                entry_result['link_action'] = 'matched'
                                entry_result['message'] = f'匹配零件 {part.get("name", part["gid"][:8])}'
                            elif len(matches) > 1:
                                entry_result['status'] = 'warn'
                                entry_result['link_action'] = 'warn'
                                entry_result['message'] = (
                                    f'vpps={entry_vpps} 在 pbom 中匹配到 {len(matches)} 条，需手动选择'
                                )
                            else:
                                entry_result['status'] = 'warn'
                                entry_result['link_action'] = 'warn'
                                entry_result['message'] = f'零件 vpps={entry_vpps} 在 pbom 中未找到'

                except Exception as ex:
                    entry_result['status'] = 'error'
                    entry_result['link_action'] = 'error'
                    entry_result['message'] = str(ex)

                results.append(entry_result)

            conn.commit()

            stats = {
                'ok':    sum(1 for r in results if r['status'] == 'ok'),
                'skip':  sum(1 for r in results if r['status'] == 'skip'),
                'warn':  sum(1 for r in results if r['status'] == 'warn'),
                'error': sum(1 for r in results if r['status'] == 'error'),
            }
            return {"data": {"stats": stats, "items": results}}


# ══════════════════════════════════════════════════════════════
# Entry-Links CRUD
# ══════════════════════════════════════════════════════════════

@router.get("/entry-links")
def list_entry_links(
    entry_gid: Optional[str] = Query(None),
    recursive: bool = Query(False),
    _u=Depends(_READ),
):
    if not entry_gid:
        raise HTTPException(400, "需要 entry_gid 参数")
    with get_conn() as conn:
        with conn.cursor() as cur:
            if not recursive:
                cur.execute(
                    "SELECT gid, entry_gid, version_gid, link_type, entity_gid, is_primary, "
                    "is_inherited, snapshot_data, created_at, created_by "
                    "FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND deleted_at IS NULL "
                    "ORDER BY created_at",
                    (entry_gid,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                # 非递归模式补充 source 字段（self）
                for r in rows:
                    r["source_entry_gid"] = r["entry_gid"]
                    r["source_entry_title"] = None
            else:
                # 递归查询：当前节点及所有后代节点的 links
                cur.execute("""
                    WITH RECURSIVE descendants AS (
                        SELECT gid, title
                        FROM workmanship_bop_bop_entries
                        WHERE gid = %s AND is_deleted = FALSE
                        UNION ALL
                        SELECT e.gid, e.title
                        FROM workmanship_bop_bop_entries e
                        JOIN descendants d ON e.parent_gid = d.gid
                        WHERE e.is_deleted = FALSE
                    )
                    SELECT l.gid, l.entry_gid, l.version_gid, l.link_type, l.entity_gid,
                           l.is_primary, l.is_inherited, l.snapshot_data, l.created_at, l.created_by,
                           d.gid AS source_entry_gid, d.title AS source_entry_title
                    FROM workmanship_bop_bop_entry_links l
                    JOIN descendants d ON l.entry_gid = d.gid
                    WHERE l.deleted_at IS NULL
                    ORDER BY d.gid, l.link_type, l.created_at
                """, (entry_gid,))
                rows = [dict(r) for r in cur.fetchall()]

            # 批量补充零件显示字段（part_no / title / vpps）
            pbom_gids = [r["entity_gid"] for r in rows if r.get("link_type") == "pbom_part"]
            if pbom_gids:
                _ph = ",".join(["%s"] * len(pbom_gids))
                cur.execute(
                    f"SELECT gid, part_no, title, vpps FROM workmanship_bop_pbom WHERE gid IN ({_ph})",
                    pbom_gids,
                )
                pbom_map = {r["gid"]: dict(r) for r in cur.fetchall()}
                for r in rows:
                    if r.get("link_type") == "pbom_part":
                        p = pbom_map.get(r["entity_gid"], {})
                        r["entity_part_no"] = p.get("part_no") or ""
                        r["entity_title"]   = p.get("title") or ""
                        r["entity_vpps"]    = p.get("vpps") or ""

    return {"data": rows}


@router.post("/entry-links", status_code=201)
def create_entry_link(body: CreateEntryLinkBody, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version_gid FROM workmanship_bop_bop_entries WHERE gid=%s",
                (body.entry_gid,),
            )
            entry = cur.fetchone()
            if not entry:
                raise HTTPException(404, "bop_entry 不存在")
            _check_version_frozen(cur, entry['version_gid'])
            _check_line_editable(cur, entry['version_gid'], body.entry_gid, _u)

            gid = str(next_gid())
            user_gid = _u.get('gid') if isinstance(_u, dict) else None
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entry_links "
                "(gid, entry_gid, version_gid, link_type, entity_gid, is_primary, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "",
                (gid, body.entry_gid, entry['version_gid'], body.link_type,
                 body.entity_gid, body.is_primary, user_gid),
            )
            _log_entry_op(cur,
                version_gid=entry['version_gid'],
                entry_gid=body.entry_gid, entry_title='',
                op_type='add_link',
                old_state=None,
                new_state={
                    'link_type': body.link_type,
                    'entity_gid': body.entity_gid,
                    'is_primary': body.is_primary,
                },
                user_gid=_u.get('gid', ''), user_name=_u.get('name', ''))
            conn.commit()
    return {"data": {"gid": gid}}


@router.delete("/entry-links/{gid}", status_code=204)
def delete_entry_link(gid: str, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT l.entry_gid, e.version_gid, l.link_type, l.entity_gid, l.is_primary, e.title AS entry_title "
                "FROM workmanship_bop_bop_entry_links l "
                "JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid "
                "WHERE l.gid=%s",
                (gid,),
            )
            row = cur.fetchone()
            if not row:
                _not_found(gid)
            _check_version_frozen(cur, row['version_gid'])
            _check_line_editable(cur, row['version_gid'], row['entry_gid'], _u)
            _log_entry_op(cur,
                version_gid=row['version_gid'],
                entry_gid=row['entry_gid'], entry_title=row.get('entry_title') or '',
                op_type='remove_link',
                old_state={
                    'link_type': row['link_type'],
                    'entity_gid': row['entity_gid'],
                    'is_primary': row['is_primary'],
                },
                new_state=None,
                user_gid=_u.get('gid', ''), user_name=_u.get('name', ''))
            cur.execute("DELETE FROM workmanship_bop_bop_entry_links WHERE gid=%s", (gid,))
            conn.commit()


# ══════════════════════════════════════════════════════════════
# Link Summary + Entity Detail
# ══════════════════════════════════════════════════════════════

@router.get("/versions/{version_gid}/link-summary")
def get_link_summary(
    version_gid: str,
    link_type: Optional[str] = Query(None),
    _u=Depends(_READ),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if link_type:
                cur.execute(
                    "SELECT l.gid, l.entry_gid, l.link_type, l.entity_gid, l.is_primary, l.snapshot_data "
                    "FROM workmanship_bop_bop_entry_links l "
                    "JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid "
                    "WHERE e.version_gid=%s AND e.is_deleted = FALSE "
                    "  AND l.link_type=%s",
                    (version_gid, link_type),
                )
            else:
                cur.execute(
                    "SELECT l.gid, l.entry_gid, l.link_type, l.entity_gid, l.is_primary, l.snapshot_data "
                    "FROM workmanship_bop_bop_entry_links l "
                    "JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid "
                    "WHERE e.version_gid=%s AND e.is_deleted = FALSE",
                    (version_gid,),
                )
            links = [dict(r) for r in cur.fetchall()]

            summary = {}
            by_type = {}
            for lnk in links:
                by_type.setdefault(lnk['link_type'], []).append(lnk)

            for lt, lt_links in by_type.items():
                table_info = _LINK_TARGET_TABLES.get(lt)
                ref_gids = list(set(l['entity_gid'] for l in lt_links))

                if table_info and ref_gids:
                    table, gid_col, deleted_col = table_info
                    where_extra = f" AND {deleted_col} IS NULL" if deleted_col else ""
                    _ph = ",".join(["%s"] * len(ref_gids))
                    try:
                        cur.execute(
                            f"SELECT {gid_col} FROM {table} "
                            f"WHERE {gid_col} IN ({_ph}){where_extra}",
                            ref_gids,
                        )
                        valid_set = set(r[gid_col] for r in cur.fetchall())
                    except Exception:
                        valid_set = set()
                else:
                    valid_set = set(ref_gids)

                for lnk in lt_links:
                    entry = {
                        'entry_gid':  lnk['entry_gid'],
                        'link_gid':   lnk['gid'],
                        'link_type':  lt,
                        'is_primary': lnk['is_primary'],
                        'is_valid':   lnk['entity_gid'] in valid_set,
                    }
                    if lnk.get('snapshot_data'):
                        entry['snapshot_data'] = lnk['snapshot_data']
                    summary[lnk['entity_gid']] = entry

    return {"data": summary}


@router.get("/entity-detail")
def get_entity_detail(
    link_type: str = Query(...),
    ref_gid: str = Query(...),
    _u=Depends(_READ),
):
    table_info = _LINK_TARGET_TABLES.get(link_type)
    if not table_info:
        raise HTTPException(400, f"未知 link_type: {link_type}")
    table, gid_col, deleted_col = table_info
    if not table:
        raise HTTPException(400, f"link_type={link_type} 暂不支持查看详情")

    with get_conn() as conn:
        with conn.cursor() as cur:
            where_extra = f" AND {deleted_col} IS NULL" if deleted_col else ""
            try:
                cur.execute(
                    f"SELECT * FROM {table} WHERE {gid_col}=%s{where_extra} LIMIT 1",
                    (ref_gid,),
                )
            except Exception:
                raise HTTPException(404, f"实体表 {table} 查询失败")
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"实体 {ref_gid} 不存在")
            data = dict(row)
            for k, v in data.items():
                if isinstance(v, (datetime, date)):
                    data[k] = v.isoformat()
                elif isinstance(v, bytes):
                    data[k] = v.decode('utf-8', errors='replace')
            data['_link_type'] = link_type
            data['_table'] = table
    return {"data": data}


@router.patch("/entity-detail")
def patch_entity_detail(body: EntityPatchBody, _u=Depends(_WRITE)):
    table_info = _LINK_TARGET_TABLES.get(body.link_type)
    if not table_info:
        raise HTTPException(400, f"未知 link_type: {body.link_type}")
    table, gid_col, deleted_col = table_info
    if not table:
        raise HTTPException(400, f"link_type={body.link_type} 暂不支持编辑")

    DENY_COLS = {'gid', 'created_at', 'created_by', 'updated_by', 'deleted_at'}
    fields = {k: v for k, v in body.fields.items() if k not in DENY_COLS and not k.startswith('_')}
    if not fields:
        raise HTTPException(400, "无可更新字段")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT l.version_gid, l.entry_gid FROM workmanship_bop_bop_entry_links l "
                "WHERE l.entity_gid=%s AND l.link_type=%s AND l.deleted_at IS NULL "
                "ORDER BY l.is_primary DESC, l.created_at ASC LIMIT 1",
                (body.ref_gid, body.link_type),
            )
            binding = cur.fetchone()
            if not binding:
                raise HTTPException(404, f"实体 {body.ref_gid} 未关联到 BOP 条目")
            _check_line_editable(cur, binding['version_gid'], binding['entry_gid'], _u)
            cur.execute(f"SELECT 1 FROM {table} WHERE {gid_col}=%s LIMIT 1", (body.ref_gid,))
            if not cur.fetchone():
                raise HTTPException(404, f"实体 {body.ref_gid} 不存在")

            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=DATABASE() AND table_name=%s",
                (table,),
            )
            real_cols = {r['column_name'] for r in cur.fetchall()}
            fields = {k: v for k, v in fields.items() if k in real_cols}
            if not fields:
                raise HTTPException(400, "无可更新字段（字段名不匹配）")

            sets = ', '.join(f"{k}=%s" for k in fields)
            vals = list(fields.values()) + [body.ref_gid]
            cur.execute(f"UPDATE {table} SET {sets} WHERE {gid_col}=%s", vals)
            conn.commit()
    return {"ok": True}


class ResolveGidsBody(BaseModel):
    gids: Dict[str, str]  # {field_name: gid_value}


@router.post("/resolve-gids")
def resolve_gids(body: ResolveGidsBody, _u=Depends(_READ)):
    """批量把 _gid 字段值解析为人类可读名称。"""
    result: dict = resolve_identity_labels(body.gids)
    with get_conn() as conn:
        with conn.cursor() as cur:
            for field, gid in body.gids.items():
                if not gid or field not in _GID_RESOLVE_MAP:
                    continue
                table, name_col = _GID_RESOLVE_MAP[field]
                try:
                    cur.execute(
                        f"SELECT {name_col} FROM {table} WHERE gid=%s LIMIT 1",
                        (gid,),
                    )
                    row = cur.fetchone()
                    if row:
                        result[field] = row[name_col]
                except Exception:
                    pass  # 表或列不存在时静默跳过
    return {"data": result}


# ══════════════════════════════════════════════════════════════
# PBOM 搜索辅助（AI 助手）
# ══════════════════════════════════════════════════════════════

@router.get("/pbom/search")
def search_pbom_parts(
    q: Optional[str] = Query(None),
    vpps: Optional[str] = Query(None),
    snapshot_gid: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    _u=Depends(_READ),
):
    like = f"%{q}%" if q else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.gid, p.part_no, p.title, p.quantity, p.unit,
                       p.vpps, p.parent_gid, p.snapshot_gid,
                       pv.version_tag
                FROM workmanship_bop_pbom p
                JOIN workmanship_bop_pbom_versions pv ON pv.gid = p.snapshot_gid
                WHERE (%s IS NULL OR p.part_no LIKE %s OR p.title LIKE %s)
                  AND (%s IS NULL OR p.vpps = %s)
                  AND (%s IS NULL OR p.snapshot_gid = %s)
                ORDER BY pv.version_tag, p.part_no
                LIMIT %s
                """,
                (like, like, like, vpps, vpps, snapshot_gid, snapshot_gid, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": rows, "total": len(rows)}


@router.get("/pbom-snapshots")
def list_pbom_snapshots(
    project_gid: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    _u=Depends(_READ),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pv.gid, pv.version_tag, pv.source_type, pv.status,
                       pv.project_gid, pv.created_at,
                       COUNT(p.gid) AS part_count
                FROM workmanship_bop_pbom_versions pv
                LEFT JOIN workmanship_bop_pbom p ON p.snapshot_gid = pv.gid
                WHERE (%s IS NULL OR pv.project_gid = %s)
                GROUP BY pv.gid, pv.version_tag, pv.source_type,
                         pv.status, pv.project_gid, pv.created_at
                ORDER BY pv.created_at DESC
                LIMIT %s
                """,
                (project_gid, project_gid, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": rows, "total": len(rows)}


@router.get("/versions/{version_gid}/line-operations")
def get_line_operations(
    version_gid: str,
    line_entry_gid: str = Query(...),
    _u=Depends(_READ),
):
    """返回指定线体下所有 operation 条目及其 process_flow_pic，
    按 sort_order DESC（拆装倒序，与截图顺序一致）。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH RECURSIVE desc_entries AS (
                    SELECT gid, title, sort_order, node_type, parent_gid, process_flow_pic, meta
                    FROM workmanship_bop_bop_entries
                    WHERE gid = %s AND is_deleted = FALSE
                    UNION ALL
                    SELECT b.gid, b.title, b.sort_order, b.node_type, b.parent_gid, b.process_flow_pic, b.meta
                    FROM workmanship_bop_bop_entries b
                    JOIN desc_entries d ON b.parent_gid = d.gid
                    WHERE b.is_deleted = FALSE
                )
                SELECT
                    gid           AS bop_entry_gid,
                    title,
                    sort_order,
                    parent_gid,
                    COALESCE(process_flow_pic, '[]')          AS process_flow_pic,
                    IFNULL(JSON_EXTRACT(meta,'$.cad_sim_pics'), '[]') AS cad_sim_pics
                FROM desc_entries
                WHERE node_type = 'operation'
                ORDER BY sort_order DESC 
                """,
                (line_entry_gid,),
            )
            rows = cur.fetchall()
    data = []
    for r in rows:
        import json as _j
        def _parse(v):
            if isinstance(v, str):
                try: return _j.loads(v)
                except: return []
            return v or []
        data.append({
            'bop_entry_gid':    r['bop_entry_gid'],
            'title':            r['title'] or '',
            'sort_order':       r['sort_order'],
            'parent_gid':       r['parent_gid'],
            'process_flow_pic': _resolve_bop_pic_items(_parse(r['process_flow_pic'])),
            'cad_sim_pics':     _parse(r['cad_sim_pics']),
        })
    return {'ok': True, 'data': data}


# ── 节点操作历史 ───────────────────────────────────────────────────────────────

@router.get("/versions/{version_gid}/history")
def get_version_history(version_gid: str, limit: int = Query(100, le=500), _u=Depends(_READ)):
    """查询整个 BOP 版本的操作历史（所有节点，时间倒序）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gid, op_type, entity_gid, entity_title, old_state, new_state,
                       performed_by, performed_by_name, performed_at, rolled_back
                FROM workmanship_bop_bop_line_operation_log
                WHERE version_gid = %s
                ORDER BY performed_at DESC
                LIMIT %s
            """, (version_gid, limit))
            rows = cur.fetchall()
    import json as _j
    result = []
    for r in rows:
        d = dict(r)
        for field in ('old_state', 'new_state'):
            if isinstance(d.get(field), str):
                try:
                    d[field] = _j.loads(d[field])
                except Exception:
                    d[field] = None
        if hasattr(d.get('performed_at'), 'isoformat'):
            d['performed_at'] = d['performed_at'].isoformat()
        result.append(d)
    return {"data": result}


@router.get("/entries/{gid}/history")
def get_entry_history(gid: str, _u=Depends(_READ)):
    """查询某条 BOP 节点的操作历史记录（最近50条，倒序）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gid, op_type, entity_title, old_state, new_state,
                       performed_by, performed_by_name, performed_at, rolled_back
                FROM workmanship_bop_bop_line_operation_log
                WHERE entity_gid = %s
                ORDER BY performed_at DESC
                LIMIT 50
            """, (gid,))
            rows = cur.fetchall()
    import json as _j
    result = []
    for r in rows:
        d = dict(r)
        for field in ('old_state', 'new_state'):
            if isinstance(d.get(field), str):
                try:
                    d[field] = _j.loads(d[field])
                except Exception:
                    d[field] = None
        if hasattr(d.get('performed_at'), 'isoformat'):
            d['performed_at'] = d['performed_at'].isoformat()
        result.append(d)
    return {"data": result}


@router.post("/entries/{gid}/history/{log_gid}/rollback")
def rollback_entry_history(gid: str, log_gid: str, _u=Depends(_WRITE)):
    """撤销一条操作记录（支持 update_entry / create_entry）"""
    import json as _j
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 获取日志记录（兼容软删除的 entry：LEFT JOIN）
            cur.execute(
                "SELECT ol.gid, ol.op_type, ol.old_state, ol.new_state, ol.rolled_back,"
                "       ol.performed_by, e.version_gid"
                " FROM workmanship_bop_bop_line_operation_log ol"
                " LEFT JOIN workmanship_bop_bop_entries e ON e.gid = ol.entity_gid"
                " WHERE ol.gid=%s AND ol.entity_gid=%s",
                (log_gid, gid),
            )
            log_row = cur.fetchone()
            if not log_row:
                raise HTTPException(404, "操作记录不存在")
            if log_row['op_type'] not in ('update_entry', 'create_entry'):
                raise HTTPException(400, "该操作类型不支持撤销")

            if not _history.can_manage_line_history(_u, log_row.get('performed_by')):
                raise HTTPException(403, "无权撤销他人的操作，请联系项目管理员")
            if log_row['rolled_back']:
                raise HTTPException(400, "该操作已回滚")

            _check_version_frozen(cur, log_row['version_gid'])

            if log_row['op_type'] == 'create_entry':
                # 回滚新建 = 软删除该节点及其 links
                cur.execute(
                    "UPDATE workmanship_bop_bop_entries"
                    " SET is_deleted=TRUE, deleted_at=NOW() WHERE gid=%s",
                    (gid,),
                )
                cur.execute(
                    "UPDATE workmanship_bop_bop_entry_links"
                    " SET deleted_at=NOW() WHERE entry_gid=%s AND deleted_at IS NULL",
                    (gid,),
                )
                # 更新父节点 child_vpps
                cur.execute(
                    "SELECT parent_gid, version_gid FROM workmanship_bop_bop_entries WHERE gid=%s",
                    (gid,),
                )
                _e = cur.fetchone()
                if _e and _e['parent_gid']:
                    _sync_child_vpps(cur, _e['parent_gid'], _e['version_gid'])

            else:  # update_entry
                old_state = log_row['old_state']
                if isinstance(old_state, str):
                    try:
                        old_state = _j.loads(old_state)
                    except Exception:
                        old_state = None
                if not old_state:
                    raise HTTPException(400, "操作记录缺少旧状态，无法回滚")

                _DIRECT_COLS = {'parent_gid', 'node_type', 'sort_order', 'title',
                                'vpps', 'vpps_desc', 'parent_bop_title'}
                restore = {k: v for k, v in old_state.items() if k in _DIRECT_COLS}
                if restore:
                    set_parts = [f"{k}=%s" for k in restore]
                    vals = list(restore.values())
                    cur.execute(
                        f"UPDATE workmanship_bop_bop_entries"
                        f" SET {','.join(set_parts)}, updated_at=NOW() WHERE gid=%s",
                        vals + [gid],
                    )

            # 标记该条日志为已回滚
            cur.execute(
                "UPDATE workmanship_bop_bop_line_operation_log"
                " SET rolled_back=TRUE WHERE gid=%s",
                (log_gid,),
            )
            conn.commit()

            # 记录一条回滚操作日志
            cur.execute(
                "SELECT title FROM workmanship_bop_bop_entries WHERE gid=%s", (gid,)
            )
            new_row = cur.fetchone()
            new_state_raw = log_row['new_state']
            if isinstance(new_state_raw, str):
                try:
                    new_state_raw = _j.loads(new_state_raw)
                except Exception:
                    new_state_raw = None
            old_state_raw = log_row['old_state']
            if isinstance(old_state_raw, str):
                try:
                    old_state_raw = _j.loads(old_state_raw)
                except Exception:
                    old_state_raw = None
            _log_entry_op(cur,
                version_gid=log_row['version_gid'],
                entry_gid=gid,
                entry_title=new_row['title'] if new_row else '',
                op_type='rollback',
                old_state=new_state_raw,
                new_state=old_state_raw,
                user_gid=_u.get('gid', ''),
                user_name=_u.get('name', ''),
            )

            cur.execute(_ENTRY_BY_GID_SQL, (gid,))
            row = cur.fetchone()
            return {"ok": True, "entry": dict(row) if row else {}}
