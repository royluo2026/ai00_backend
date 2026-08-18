"""
backend/routers/_bop/_helpers.py
────────────────────────────────
BOP 子包共享辅助函数。
"""
import json
import logging
import os
from typing import Mapping, Optional

from fastapi import HTTPException

from ...data.connection import get_conn
from backend.platform_sdk.ids import next_gid

from ._constants import (
    _LINK_SNAPSHOT_MAP,
    _DEEP_COPY_ENTITY_TABLES,
    _SHARED_ENTITY_LINK_TYPES,
    _SKIP_LINK_TYPES,
    _AI00_LEVEL,
    _ENTRY_LIST_SQL,
)

_log = logging.getLogger(__name__)


def legacy_entries_max_from_env(environ: Mapping[str, str] | None = None) -> int:
    """Read the bounded compatibility limit and fail fast on bad deployment config."""
    source = os.environ if environ is None else environ
    name = "AI00_CRAFT_LEGACY_ENTRIES_MAX"
    raw = source.get(name)
    if raw is None:
        return 2_000
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0 or str(value) != str(raw).strip():
        raise RuntimeError(f"{name} must be a positive integer")
    return value


# ── MySQL IN 展开辅助 ─────────────────────────────────────────────────────────

def sql_in(items):
    """返回 (IN子句占位符, 参数列表)，空列表时返回 (1=0, []) 保证语义正确。"""
    if not items:
        return "1=0", []
    placeholders = ",".join(["%s"] * len(items))
    return f"IN ({placeholders})", list(items)




import json as _json

# JSON 类型字段列表（MySQL 返回字符串，需要自动解析）
_JSON_FIELDS = frozenset({
    'meta', 'ext', 'params', 'child_vpps', 'entity_data', 'snapshot_data',
    'process_flow_pic', 'process_chart_pic', 'image_ref', 'steps',
    'required_tools', 'parameters',
})


def _parse_row(d: dict) -> dict:
    """将 dict 中的 JSON 字符串字段解析为 Python 对象。"""
    for k, v in d.items():
        if k in _JSON_FIELDS and isinstance(v, str) and v.strip():
            try:
                d[k] = _json.loads(v)
            except (_json.JSONDecodeError, ValueError):
                pass
    return d


def _row(cur, keys=None):
    """将 cur.fetchone() 转为 dict（RealDictCursor 直接 dict(row)）"""
    row = cur.fetchone()
    if row is None:
        return None
    return _parse_row(dict(row))


def _rows(cur, keys=None):
    return [_parse_row(dict(r)) for r in cur.fetchall()]


def _not_found(gid):
    raise HTTPException(status_code=404, detail=f"记录 {gid} 不存在")


# ── 版本状态检查 ──────────────────────────────────────────────────────────────

def _check_version_frozen(cur, version_gid: str):
    """若版本非 active 则抛 403"""
    cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
    row = cur.fetchone()
    if row and row['status'] != 'active':
        raise HTTPException(403, f"版本状态为 {row['status']}，不允许修改")


def _check_frozen_by_version(version_gid: str):
    """独立连接检查版本冻结（用于不带 cursor 的场景）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            _check_version_frozen(cur, version_gid)


# ── 快照机制 ─────────────────────────────────────────────────────────────────

def _snapshot_links(cur, version_gid: str):
    """为版本的所有 entry_links 写入 snapshot_data（冻结时调用）"""
    cur.execute(
        "SELECT l.gid, l.link_type, l.entity_gid "
        "FROM workmanship_bop_bop_entry_links l "
        "JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid "
        "WHERE e.version_gid = %s AND e.is_deleted = FALSE",
        (version_gid,),
    )
    all_links = [dict(r) for r in cur.fetchall()]
    if not all_links:
        return

    by_type = {}
    for lk in all_links:
        by_type.setdefault(lk['link_type'], []).append(lk)

    for lt, links in by_type.items():
        snap_info = _LINK_SNAPSHOT_MAP.get(lt)
        if not snap_info:
            continue
        table, cols = snap_info
        entity_gids = list(set(lk['entity_gid'] for lk in links))
        col_str = '*' if cols is None else ', '.join(cols)
        try:
            in_clause, in_params = sql_in(entity_gids)
            cur.execute(
                f"SELECT {col_str} FROM {table} WHERE gid {in_clause}",
                in_params,
            )
            snap_rows = {dict(r)['gid']: dict(r) for r in cur.fetchall()}
        except Exception:
            snap_rows = {}

        for lk in links:
            snap = snap_rows.get(lk['entity_gid'])
            if snap:
                cur.execute(
                    "UPDATE workmanship_bop_bop_entry_links SET snapshot_data = %s WHERE gid = %s",
                    (json.dumps(snap, default=str), lk['gid']),
                )


def _clear_snapshots(cur, version_gid: str):
    """清除版本所有 entry_links 的 snapshot_data（解冻时调用）"""
    cur.execute(
        "UPDATE workmanship_bop_bop_entry_links l "
        "SET snapshot_data = NULL "
        "FROM workmanship_bop_bop_entries e "
        "WHERE l.entry_gid = e.gid "
        "  AND e.version_gid = %s "
        "  AND e.is_deleted = FALSE",
        (version_gid,),
    )


# ── 条目层级辅助 ──────────────────────────────────────────────────────────────

def _parent_level(cur, parent_gid: Optional[str]) -> int:
    """查询父节点的 level，返回其 level+1；无父节点则返回 0"""
    if not parent_gid:
        return 0
    cur.execute("SELECT level FROM workmanship_bop_bop_entries WHERE gid=%s", (parent_gid,))
    row = cur.fetchone()
    return (row['level'] + 1) if row else 0


def _get_entry_line_gid(cur, entry_gid: str) -> Optional[str]:
    cur.execute("""
        WITH RECURSIVE ancestors AS (
            SELECT gid, parent_gid, node_type
            FROM workmanship_bop_bop_entries
            WHERE gid=%s
            UNION ALL
            SELECT e.gid, e.parent_gid, e.node_type
            FROM workmanship_bop_bop_entries e
            JOIN ancestors a ON a.parent_gid = e.gid
        )
        SELECT gid FROM ancestors WHERE node_type='line_process' LIMIT 1
    """, (entry_gid,))
    row = cur.fetchone()
    return row['gid'] if row else None



def _check_line_editable(cur, version_gid: str, entry_gid: str, user: dict, allow_copy: bool = False):
    from backend.platform_sdk.auth import get_user_grants, derive_org_role

    org_role = user.get('org_role') or derive_org_role(user.get('system_role', 'external'))
    # 组织成员可编辑所有工艺流程图，不再受项目负责人或线体负责人范围限制。
    if org_role in ('super_admin', 'member', 'team_admin', 'project_admin'):
        return

    cur.execute("SELECT project_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
    ver = cur.fetchone()
    project_gid = ver['project_gid'] if ver else None
    grants = get_user_grants(user.get('gid', ''))
    if project_gid and any(g['grant_type'] == 'project_owner' and g.get('scope_gid') == project_gid for g in grants):
        return

    line_gid = _get_entry_line_gid(cur, entry_gid)
    if line_gid and any(g['grant_type'] == 'section_lead' and g.get('scope_gid') == line_gid for g in grants):
        return

    if allow_copy:
        return
    raise HTTPException(403, "当前线体无编辑权限（只读）")


def _sync_entry_title(cur, entity_gid: str, new_title: str):
    """实体表 title 变更后，同步到 bop_entries（跳过冻结版本）"""
    cur.execute("""
        UPDATE workmanship_bop_bop_entries e
          JOIN workmanship_bop_bop_entry_links el ON el.entry_gid = e.gid
          JOIN workmanship_bop_bop_versions v    ON v.gid = el.version_gid
           SET e.title = %s
         WHERE el.entity_gid = %s
           AND el.is_primary = TRUE
           AND v.frozen_at   IS NULL
    """, (new_title, entity_gid))


def _sync_child_vpps(cur, parent_gid: str, version_gid: str):
    """重建父节点的 child_vpps 数组（跳过冻结版本）"""
    cur.execute("SELECT frozen_at FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
    ver = cur.fetchone()
    if ver and ver['frozen_at']:
        return
    cur.execute("""
        SELECT e.gid, e.node_type, e.title,
               COALESCE(
                   (SELECT en.vpps FROM (
                       SELECT ln.vpps FROM workmanship_bop_bop_line ln
                         JOIN workmanship_bop_bop_entry_links lnk ON lnk.entity_gid = ln.gid
                        WHERE lnk.entry_gid = e.gid AND lnk.is_primary = TRUE
                          AND lnk.link_type = 'bop_line'
                       UNION ALL
                       SELECT st.vpps FROM workmanship_bop_bop_station st
                         JOIN workmanship_bop_bop_entry_links lnk ON lnk.entity_gid = st.gid
                        WHERE lnk.entry_gid = e.gid AND lnk.is_primary = TRUE
                          AND lnk.link_type = 'bop_station'
                       UNION ALL
                       SELECT pr.vpps FROM workmanship_bop_bop_process pr
                         JOIN workmanship_bop_bop_entry_links lnk ON lnk.entity_gid = pr.gid
                        WHERE lnk.entry_gid = e.gid AND lnk.is_primary = TRUE
                          AND lnk.link_type = 'bop_process'
                       UNION ALL
                       SELECT op.vpps FROM workmanship_bop_bop_steps op
                         JOIN workmanship_bop_bop_entry_links lnk ON lnk.entity_gid = op.gid
                        WHERE lnk.entry_gid = e.gid AND lnk.is_primary = TRUE
                          AND lnk.link_type = 'bop_steps'
                   ) en LIMIT 1),
                   e.vpps, ''
               ) AS vpps
          FROM workmanship_bop_bop_entries e
         WHERE e.parent_gid   = %s
           AND e.version_gid  = %s
           AND e.is_deleted   = FALSE
    """, (parent_gid, version_gid))
    children = cur.fetchall()
    child_vpps = [
        {"vpps": c['vpps'], "node_type": c['node_type'], "title": c['title'] or ''}
        for c in children if c['vpps']
    ]
    cur.execute(
        "UPDATE workmanship_bop_bop_entries SET child_vpps=%s WHERE gid=%s",
        (json.dumps(child_vpps), parent_gid)
    )


# ── 实体深拷贝 ────────────────────────────────────────────────────────────────

def _deep_copy_entity(cur, link_type: str, entity_gid: str, project_gid: str) -> str:
    """深拷贝实体表记录，清空文件字段，返回新 gid。
    如 link_type 不在支持列表则返回原 gid（共享引用）。"""
    entry = _DEEP_COPY_ENTITY_TABLES.get(link_type)
    if not entry:
        return entity_gid

    table, file_fields = entry
    cur.execute(f"SELECT * FROM {table} WHERE gid=%s", (entity_gid,))
    row = cur.fetchone()
    if not row:
        return entity_gid

    new_ent_gid = str(next_gid())
    data = dict(row)
    data['gid'] = new_ent_gid
    if 'project_gid' in data and project_gid:
        data['project_gid'] = project_gid
    for field in file_fields:
        if field in data:
            data[field] = None
    for ts_field in ('created_at', 'updated_at', 'deleted_at', 'archived_at'):
        if ts_field in data:
            del data[ts_field]
    for flag in ('is_deleted', 'is_archived'):
        if flag in data:
            data[flag] = False

    cols = ', '.join(data.keys())
    placeholders = ', '.join(['%s'] * len(data))
    cur.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        list(data.values()),
    )
    return new_ent_gid


def _do_copy(version_gid: str, src_gid: str, set_gbop_source: bool,
             cut_node_types: Optional[set] = None):
    """复制 bop_entries + links + 实体表到目标版本。
    cut_node_types: 不复制这些 node_type 的 entries 及其子树（用于 template 截断）。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT project_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (src_gid,))
            src_ver_row = cur.fetchone()
            project_gid = src_ver_row['project_gid'] if src_ver_row else None

            cur.execute(_ENTRY_LIST_SQL, (src_gid,))
            src_rows = [dict(r) for r in cur.fetchall()]
            if not src_rows:
                return {"data": [], "count": 0}

            if cut_node_types:
                cut_entry_gids: set = set()
                for r in src_rows:
                    if r['node_type'] in cut_node_types:
                        cut_entry_gids.add(r['gid'])
                changed = True
                while changed:
                    changed = False
                    for r in src_rows:
                        if r['gid'] not in cut_entry_gids and r.get('parent_gid') in cut_entry_gids:
                            cut_entry_gids.add(r['gid'])
                            changed = True
                src_rows = [r for r in src_rows if r['gid'] not in cut_entry_gids]

            gid_map = {r['gid']: str(next_gid()) for r in src_rows}

            for r in src_rows:
                new_gid    = gid_map[r['gid']]
                new_parent = gid_map.get(r['parent_gid']) if r['parent_gid'] else None
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entries "
                    "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, parent_bop_title, child_vpps, meta) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}')",
                    (new_gid, version_gid, new_parent,
                     r['node_type'], r['sort_order'], r.get('level', 0),
                     _AI00_LEVEL.get(r['node_type']),
                     r.get('title'), r.get('vpps'), r.get('vpps_desc'),
                     r.get('parent_bop_title'),
                     json.dumps(r.get('child_vpps') or []))
                )

            cur.execute(
                "SELECT gid, entry_gid, link_type, entity_gid, is_primary,"
                " is_inherited, snapshot_data"
                " FROM workmanship_bop_bop_entry_links"
                " WHERE version_gid=%s AND is_deleted = FALSE",
                (src_gid,),
            )
            src_links = [dict(r) for r in cur.fetchall()]

            for lnk in src_links:
                if lnk['link_type'] in _SKIP_LINK_TYPES:
                    continue
                new_entry_gid = gid_map.get(lnk['entry_gid'])
                if not new_entry_gid:
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
                    (str(next_gid()), new_entry_gid, version_gid,
                     lnk['link_type'], new_ent_gid,
                     lnk['is_primary'], lnk.get('is_inherited', False)),
                )

            parent_gids_to_sync: set = set()
            for r in src_rows:
                if r.get('parent_gid') and gid_map.get(r['parent_gid']):
                    parent_gids_to_sync.add(gid_map[r['parent_gid']])
            for pg in parent_gids_to_sync:
                _sync_child_vpps(cur, pg, version_gid)

            conn.commit()
            return {"data": [], "count": len(gid_map)}


# ── Auto-link 规则检查 ────────────────────────────────────────────────────────

def _check_auto_link_rules(cur, entry: dict, version_gid: str) -> list:
    """预留：校验 auto-link 相关规则。当前返回空列表。"""
    return []


# ── Smart Fork 实体复制 ───────────────────────────────────────────────────────

def _copy_entity_for_fork(cur, link_type: str, entity_gid: str, project_gid: str) -> str:
    """复制实体表记录，返回新 gid（如不在支持列表则返回原 gid 共享）"""
    _ENTITY_TABLES = {
        'bop_line':     'workmanship_bop_bop_line',
        'bop_station':  'workmanship_bop_bop_station',
        'bop_process':  'workmanship_bop_bop_process',
        'bop_steps':    'workmanship_bop_bop_steps',
        'bop_operator': 'workmanship_bop_bop_operator',
    }
    table = _ENTITY_TABLES.get(link_type)
    if not table:
        return entity_gid

    cur.execute(f"SELECT * FROM {table} WHERE gid=%s", (entity_gid,))
    row = cur.fetchone()
    if not row:
        return entity_gid

    new_ent_gid = str(next_gid())
    data = dict(row)
    data['gid'] = new_ent_gid
    if 'project_gid' in data:
        data['project_gid'] = project_gid
    cols = ', '.join(data.keys())
    placeholders = ', '.join(['%s'] * len(data))
    cur.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        list(data.values()),
    )
    return new_ent_gid


# ── 冻结快照：复制 entries + links（供 freeze-snapshot 和 stage_advance 共用）─────

def _copy_entries_and_links(cur, src_version_gid: str, new_version_gid: str) -> dict:
    """
    将 src_version_gid 的所有 bop_entries 和 bop_entry_links 复制到 new_version_gid。
    - bop_entries：新 GID，source_entry_gid = 原 GID，parent_gid 按映射重写
    - bop_entry_links：新 GID，entry_gid 指向新条目，跳过 _SKIP_LINK_TYPES
    返回 gid_map（旧 GID → 新 GID）。
    """
    cur.execute(
        "SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
        " title, vpps, vpps_desc, parent_bop_title, child_vpps,"
        " vpps_part, catia_occurrence_name, parent_vpps_name,"
        " owner_gid, meta"
        " FROM workmanship_bop_bop_entries"
        " WHERE version_gid=%s AND is_deleted=FALSE"
        " ORDER BY sort_order",
        (src_version_gid,),
    )
    src_entries = [dict(r) for r in cur.fetchall()]

    if not src_entries:
        return {}

    gid_map = {e['gid']: str(next_gid()) for e in src_entries}

    for e in src_entries:
        new_gid    = gid_map[e['gid']]
        new_parent = gid_map.get(e['parent_gid']) if e['parent_gid'] else None
        src_meta   = e.get('meta') or {}
        if isinstance(src_meta, str):
            try:    src_meta = json.loads(src_meta)
            except: src_meta = {}
        cur.execute(
            "INSERT INTO workmanship_bop_bop_entries "
            "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
            " title, vpps, vpps_desc, parent_bop_title, child_vpps,"
            " vpps_part, catia_occurrence_name, parent_vpps_name,"
            " owner_gid, meta, source_entry_gid) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (new_gid, new_version_gid, new_parent,
             e['node_type'], e['sort_order'], e.get('level', 0),
             _AI00_LEVEL.get(e['node_type']),
             e.get('title'), e.get('vpps'), e.get('vpps_desc'),
             e.get('parent_bop_title'),
             json.dumps(e.get('child_vpps') or []),
             e.get('vpps_part') or '', e.get('catia_occurrence_name') or '',
             e.get('parent_vpps_name') or '',
             e.get('owner_gid'), json.dumps(src_meta),
             e['gid'])
        )

    cur.execute(
        "SELECT entry_gid, link_type, entity_gid, is_primary, is_inherited"
        " FROM workmanship_bop_bop_entry_links"
        " WHERE version_gid=%s"
        "   AND (is_deleted IS NULL OR is_deleted=FALSE)",
        (src_version_gid,),
    )
    for lnk in [dict(r) for r in cur.fetchall()]:
        if lnk['link_type'] in _SKIP_LINK_TYPES:
            continue
        new_entry_gid = gid_map.get(lnk['entry_gid'])
        if not new_entry_gid:
            continue
        cur.execute(
            "INSERT INTO workmanship_bop_bop_entry_links "
            "(gid, entry_gid, version_gid, link_type, entity_gid,"
            " is_primary, is_inherited) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (str(next_gid()), new_entry_gid, new_version_gid,
             lnk['link_type'], lnk['entity_gid'],
             lnk['is_primary'], lnk.get('is_inherited', False)),
        )

    return gid_map


# ── 操作日志辅助 ───────────────────────────────────────────────────────────────

def _get_line_gid(cur, entry_gid: str) -> Optional[str]:
    """迭代向上找 line_process 祖先节点 gid（最多20层）"""
    gid = entry_gid
    for _ in range(20):
        cur.execute(
            "SELECT parent_gid, node_type FROM workmanship_bop_bop_entries "
            "WHERE gid=%s AND is_deleted=FALSE",
            (gid,)
        )
        row = cur.fetchone()
        if not row:
            return None
        if row['node_type'] == 'line_process':
            return gid
        if not row['parent_gid']:
            return None
        gid = row['parent_gid']
    return None


def _log_entry_op(cur, *, version_gid: str, entry_gid: str, entry_title: str,
                  op_type: str, old_state, new_state,
                  user_gid: str, user_name: str) -> tuple[str, str]:
    """向 bop_line_operation_log 写一条操作记录；失败静默不阻断主事务。
    返回 (batch_id, line_gid) 供前端刷新操作历史面板。"""
    # 确保表有 old_state / new_state 列
    line_gid = _get_line_gid(cur, entry_gid) or entry_gid
    batch_id = str(next_gid())
    try:
        cur.execute(
            "INSERT INTO workmanship_bop_bop_line_operation_log"
            " (gid, version_gid, line_gid, batch_id, op_type,"
            "  entity_gid, entity_title, old_state, new_state,"
            "  performed_by, performed_by_name, performed_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            (
                str(next_gid()), version_gid, line_gid, batch_id, op_type,
                entry_gid, entry_title,
                json.dumps(old_state, default=str) if old_state is not None else None,
                json.dumps(new_state, default=str) if new_state is not None else None,
                user_gid, user_name,
            )
        )
        _log.debug("oplog ok gid=%s op=%s batch=%s", entry_gid, op_type, batch_id)
    except Exception as exc:
        import traceback as _tb
        _log.warning("oplog write failed gid=%s op=%s: %s\n%s",
                     entry_gid, op_type, exc, _tb.format_exc())
    return batch_id, line_gid
