"""工艺关系演示：按隐藏编码连接/恢复工位-工序-操作-零件关系。

仅作用于 bop_versions.meta.demo.relation_demo=true 的专用演示版本；
超管或服务器配置的测试演示账号可操作；演示账号仅可操作 L5 演示版本。
connect: 按 bop_station.ext.demo_process_codes 把停靠在「待连接工序区」的
工序移回对应工位（操作随工序），并按 bop_steps.ext.demo_part_codes 与
pbom.meta.demo_code 建立操作到零件的装配零件直接关系（带 demo 标记）。
reset: 把演示编码工序移回待连接区并软删带 demo 标记的装配零件链接。
status: 只读查询各线体当前连接状态及完整 steps（幂等重连/刷新后播放用）。

性能：移动计算全部在内存中规划，最后按 CASE/IN 批量落库，
实际耗时受数据库执行影响，可通过服务端诊断区分读取、规划和批量写入。
"""
from __future__ import annotations

import json
from copy import deepcopy
import os
import sys
import time
from contextlib import contextmanager
from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilitySpec,
)
from backend.capability_v2.reliability import TransactionalCapabilityOutput, transactional_provider

OPERATIONS = ("connect", "reset", "status")
DEMO_LINK_TAG = "w10_relation"
DEMO_CODE_PREFIX = "W10D-"
HOLDING_META_KEY = "demo_holding"
PART_NODE_TYPES = ("part", "standard_part", "non_standard_part", "support_material")
_FLUSH_CHUNK = 200
_PLAN_NODE_LIMIT = 20000
_PLAN_NODE_TYPES = ('line_process', 'station_process', 'operator_process', 'process')
_DIAGNOSTIC_PHASES = frozenset((
    'version_auth', 'tree', 'holding', 'station_links', 'station_codes',
    'step_links', 'step_codes', 'process_codes', 'pbom', 'existing_links',
    'planning', 'canonical_plan', 'restore_links', 'insert_links', 'move_flush', 'remove_links',
    'connect_total', 'reset_total', 'status_total',
))


class _DiagnosticCursor:
    """Opt-in timing; never retain or log SQL, parameters, rows or identities."""
    def __init__(self, cursor):
        self.cursor = cursor
        self.sql_count = 0
        self.sql_seconds = 0.0

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def _call(self, name, *args, **kwargs):
        started = time.perf_counter()
        if name in ('execute', 'executemany'):
            self.sql_count += 1
        try:
            return getattr(self.cursor, name)(*args, **kwargs)
        finally:
            self.sql_seconds += time.perf_counter() - started

    def execute(self, *args, **kwargs):return self._call('execute', *args, **kwargs)
    def executemany(self, *args, **kwargs):return self._call('executemany', *args, **kwargs)
    def fetchone(self, *args, **kwargs):return self._call('fetchone', *args, **kwargs)
    def fetchall(self, *args, **kwargs):return self._call('fetchall', *args, **kwargs)


def _diagnostic_cursor(cursor):
    return _DiagnosticCursor(cursor) if os.getenv('AI00_DEMO_CAPACITY_DIAGNOSTICS') == '1' else cursor


@contextmanager
def _diagnostic_phase(cursor, phase):
    if phase not in _DIAGNOSTIC_PHASES:
        raise ValueError('unknown diagnostic phase')
    if not isinstance(cursor, _DiagnosticCursor):
        yield
        return
    started = time.perf_counter()
    count, seconds = cursor.sql_count, cursor.sql_seconds
    try:
        yield
    finally:
        print(json.dumps({'demo_relation_timing': True, 'phase': phase,
            'seconds': round(time.perf_counter() - started, 6),
            'sql_seconds': round(cursor.sql_seconds - seconds, 6),
            'sql_count': cursor.sql_count - count}), file=sys.stderr, flush=True)


def _phase_call(cursor, phase, function, *args):
    with _diagnostic_phase(cursor, phase):
        return function(*args)


def _parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return default
    return parsed if parsed is not None else default


def _require_super_admin(context: CapabilityContext) -> None:
    from backend.platform_sdk.demo_access import has_relation_demo_access
    if "super_admin" not in set(context.active_roles or ()) and not has_relation_demo_access(context.user_gid):
        raise CapabilityBusinessError("demo_super_admin_required", "演示功能仅超级管理员可用")


def _require_demo_version(cur: Any, bop_gid: str, context: CapabilityContext | None = None) -> None:
    cur.execute(
        "SELECT v.gid, v.meta, v.frozen_at, v.project_gid, p.project_code "
        "FROM workmanship_bop_bop_versions v "
        "JOIN workmanship_proj_projects p ON p.gid=v.project_gid AND p.is_deleted=FALSE "
        "WHERE v.gid=%s AND v.is_deleted=FALSE",
        (bop_gid,),
    )
    row = cur.fetchone()
    if not row:
        raise CapabilityBusinessError("demo_version_not_found", f"BOP 版本 {bop_gid} 不存在", retryable=False)
    if context is not None and "super_admin" not in set(context.active_roles or ()):
        from backend.platform_sdk.demo_access import has_relation_demo_access
        if row.get('project_code') != 'L5' or not has_relation_demo_access(context.user_gid, str(row.get('project_gid') or '')):
            raise CapabilityBusinessError('demo_project_scope_denied', '演示账号不能操作此项目')
        from backend.platform_sdk.project_access import can_edit_project_bop
        if not can_edit_project_bop(context.user_gid, str(row['project_gid']), None, context.active_roles):
            raise CapabilityBusinessError('demo_project_responsibility_required', '演示账号当前没有此项目的工艺编辑职责')
    if row.get("frozen_at"):
        raise CapabilityBusinessError("demo_version_frozen", "BOP 版本已冻结，不允许演示修改")
    meta = _parse_json(row.get("meta"), {})
    if not (isinstance(meta.get("demo"), dict) and meta["demo"].get("relation_demo")):
        raise CapabilityBusinessError("demo_version_required", "该版本未标记为工艺关系演示版本，拒绝演示修改")


def _load_tree(cur: Any, bop_gid: str, source_skeleton: bool = False) -> tuple[dict, dict]:
    skeleton_filter = " AND node_type IN ('line_process','station_process','operator_process','process')" if source_skeleton else ""
    limit = " LIMIT 20001" if source_skeleton else ""
    cur.execute(
        "SELECT gid, parent_gid, node_type, level, sort_order, title, "
        "CASE WHEN node_type IN ('line_process','station_process','operator_process','process') "
        "THEN meta ELSE NULL END AS meta, version_gid, source_entry_gid "
        "FROM workmanship_bop_bop_entries WHERE version_gid=%s AND is_deleted=FALSE" + skeleton_filter + limit,
        (bop_gid,),
    )
    info: dict = {}
    children: dict = {}
    for row in cur.fetchall():
        if row['gid'] in info or (source_skeleton and len(info) >= _PLAN_NODE_LIMIT):
            raise CapabilityBusinessError('demo_relation_plan_invalid', '演示关系节点重复或超过安全读取范围')
        info[row["gid"]] = dict(row)
        children.setdefault(row["parent_gid"], []).append(row["gid"])
    for gid_list in children.values():
        gid_list.sort(key=lambda g: (info[g].get("sort_order") or 0))
    return info, children


def _descendants(children: dict, gid: str) -> list:
    out, stack = [], [gid]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            out.append(child)
            stack.append(child)
    return out


class _MovePlanner:
    """在内存中规划移动，最后批量落库。"""

    def __init__(self, info: dict, children: dict):
        self.info = info
        self.children = children
        self.moves: list = []        # (gid, new_parent, sort_order, new_level)
        self.level_updates: dict = {}  # gid -> new_level（不含 moves 里的根）

    def next_sort(self, parent_gid: str) -> float:
        existing = [self.info[g].get("sort_order") or 0 for g in self.children.get(parent_gid, [])]
        return (max(existing) if existing else 0) + 10

    def move(self, entry_gid: str, new_parent: str) -> None:
        entry = self.info[entry_gid]
        new_level = (self.info[new_parent].get("level") or 0) + 1
        delta = new_level - (entry.get("level") or 0)
        sort_order = self.next_sort(new_parent)
        self.moves.append((entry_gid, new_parent, sort_order, new_level))
        if delta:
            for gid in _descendants(self.children, entry_gid):
                self.level_updates[gid] = (self.info[gid].get("level") or 0) + delta
        old_parent = entry.get("parent_gid")
        if old_parent in self.children and entry_gid in self.children[old_parent]:
            self.children[old_parent].remove(entry_gid)
        self.children.setdefault(new_parent, []).append(entry_gid)
        entry["parent_gid"] = new_parent
        entry["sort_order"] = sort_order
        entry["level"] = new_level

    def flush(self, cur: Any) -> None:
        for i in range(0, len(self.moves), _FLUSH_CHUNK):
            chunk = self.moves[i:i + _FLUSH_CHUNK]
            parent_case = " ".join("WHEN %s THEN %s" for _ in chunk)
            sort_case = " ".join("WHEN %s THEN %s" for _ in chunk)
            level_case = " ".join("WHEN %s THEN %s" for _ in chunk)
            placeholders = ",".join(["%s"] * len(chunk))
            params: list = []
            for gid, parent, _sort, _level in chunk:
                params.extend((gid, parent))
            for gid, _parent, sort, _level in chunk:
                params.extend((gid, sort))
            for gid, _parent, _sort, level in chunk:
                params.extend((gid, level))
            params.extend(gid for gid, _p, _s, _l in chunk)
            cur.execute(
                "UPDATE workmanship_bop_bop_entries SET "
                f"parent_gid=CASE gid {parent_case} END, "
                f"sort_order=CASE gid {sort_case} END, "
                f"level=CASE gid {level_case} END, "
                "updated_at=NOW(6) "
                f"WHERE gid IN ({placeholders})",
                params,
            )
        level_items = [(gid, lv) for gid, lv in self.level_updates.items() if lv is not None]
        for i in range(0, len(level_items), _FLUSH_CHUNK):
            chunk = level_items[i:i + _FLUSH_CHUNK]
            level_case = " ".join("WHEN %s THEN %s" for _ in chunk)
            placeholders = ",".join(["%s"] * len(chunk))
            params = []
            for gid, lv in chunk:
                params.extend((gid, lv))
            params.extend(gid for gid, _lv in chunk)
            cur.execute(
                "UPDATE workmanship_bop_bop_entries SET "
                f"level=CASE gid {level_case} END, updated_at=NOW(6) "
                f"WHERE gid IN ({placeholders})",
                params,
            )


def _entity_links(cur: Any, bop_gid: str, link_type: str) -> dict:
    cur.execute(
        "SELECT l.entry_gid, l.entity_gid FROM workmanship_bop_bop_entry_links l "
        "JOIN workmanship_bop_bop_entries e ON e.gid=l.entry_gid AND e.is_deleted=FALSE "
        "WHERE e.version_gid=%s AND l.is_deleted=FALSE AND l.link_type=%s",
        (bop_gid, link_type),
    )
    return {row["entry_gid"]: row["entity_gid"] for row in cur.fetchall()}


def _holding_line(cur: Any, bop_gid: str, info: dict | None = None) -> str:
    if info is None:
        cur.execute(
            "SELECT gid, meta FROM workmanship_bop_bop_entries "
            "WHERE version_gid=%s AND is_deleted=FALSE AND node_type='line_process'",
            (bop_gid,),
        )
        rows = cur.fetchall()
    else:
        # This complete tree was read in this operation's current transaction.
        rows = (row for row in info.values() if row['node_type'] == 'line_process')
    for row in rows:
        if _parse_json(row.get("meta"), {}).get(HOLDING_META_KEY):
            return row["gid"]
    raise CapabilityBusinessError("demo_holding_line_missing", "演示版本缺少「待连接工序区」线体")


def _canonical_relation_plan(clone_version: dict, source_version: dict, clone_nodes: list, source_nodes: list) -> dict:
    """Derive only real source processes; the original parent remains their target.

    This internal projection does not persist metadata or create entities. Existing
    codes, operation links and PBOM mappings are retained unchanged.
    """
    def invalid():
        raise CapabilityBusinessError('demo_relation_plan_invalid', '演示关系来源或节点映射无效')

    clone_gid, source_gid = str(clone_version.get('gid') or ''), str(source_version.get('gid') or '')
    meta = _parse_json(clone_version.get('meta'), {})
    demo = meta.get('demo') if isinstance(meta, dict) else None
    if (not isinstance(demo, dict) or not demo.get('relation_demo') or not clone_gid or not source_gid
            or clone_gid == source_gid or str(demo.get('source_version_gid') or '') != source_gid
            or not clone_version.get('project_gid')
            or clone_version.get('project_gid') != source_version.get('project_gid')
            or clone_version.get('is_deleted') or source_version.get('is_deleted')):
        invalid()
    raw = demo.get('relation_plan')
    if not isinstance(raw, dict) or not raw:
        invalid()
    plan = deepcopy(raw)
    for key in ('station_codes', 'process_codes', 'operation_part_codes', 'pbom_codes'):
        if not isinstance(plan.get(key), dict): invalid()

    def indexed(nodes, version):
        if len(nodes) > _PLAN_NODE_LIMIT: invalid()
        result = {}
        for node in nodes:
            if (not isinstance(node.get('gid'), str)
                    or (node.get('parent_gid') is not None and not isinstance(node.get('parent_gid'), str))): invalid()
            gid = str(node.get('gid') or '')
            if (not gid or gid in result or str(node.get('version_gid') or '') != version
                    or node.get('is_deleted')): invalid()
            result[gid] = node
        # Memoized ancestry validation is linear, including deep trees.
        checked = set()
        for gid in result:
            path = set(); current = gid
            while current and current not in checked:
                if current in path or current not in result: invalid()
                path.add(current)
                current = str(result[current].get('parent_gid') or '')
            checked.update(path)
        return result

    source = indexed(source_nodes, source_gid); clone = indexed(clone_nodes, clone_gid)
    mapping = {}; holding = set()
    for gid, node in clone.items():
        if node.get('node_type') not in _PLAN_NODE_TYPES: continue
        if node.get('source_entry_gid') is not None and not isinstance(node.get('source_entry_gid'), str): invalid()
        origin = str(node.get('source_entry_gid') or '')
        if not origin:
            node_meta = _parse_json(node.get('meta'), {})
            if (node.get('node_type') != 'line_process' or node.get('parent_gid')
                    or not isinstance(node_meta, dict) or not node_meta.get(HOLDING_META_KEY)): invalid()
            holding.add(gid); continue
        if origin not in source or origin in mapping or node.get('node_type') != source[origin].get('node_type'):
            invalid()
        mapping[origin] = gid
    if len(holding) != 1: invalid()
    # Every retained anchor/subtree edge must still follow the cloned source.
    # Process roots alone may be parked in the holding line by normal Reset.
    for origin, gid in mapping.items():
        node = clone[gid]; parent = source[origin].get('parent_gid')
        target = mapping.get(str(parent)) if parent else None
        if parent and target is None: invalid()
        actual = node.get('parent_gid')
        if actual != target and not (node.get('node_type') == 'process' and actual in holding): invalid()

    code_station = {}; targets = {}; existing_processes = set()
    for station, codes in plan['station_codes'].items():
        if (not isinstance(codes, list) or station not in clone
                or clone[station].get('node_type') != 'station_process' or clone[station].get('level') != 2): invalid()
        for code in codes:
            if not isinstance(code, str) or code in code_station: invalid()
            code_station[code] = station
    for code, gid in plan['process_codes'].items():
        if not isinstance(code, str) or gid not in clone or clone[gid].get('node_type') != 'process' or gid in existing_processes:
            invalid()
        if code not in code_station: invalid()
        existing_processes.add(gid)
    if set(code_station) != set(plan['process_codes']): invalid()

    process_to_code = {gid: code for code, gid in plan['process_codes'].items()}
    for origin, node in sorted(source.items(), key=lambda item: (item[1].get('sort_order') or 0, item[0])):
        if node.get('node_type') != 'process': continue
        gid = mapping.get(origin)
        if gid is None: invalid()
        parent_gid = str(node.get('parent_gid') or '')
        parent = source.get(parent_gid)
        if parent is None: invalid()
        station_gid = parent_gid
        if parent.get('node_type') == 'operator_process':
            if parent.get('level') != 3: invalid()
            station_gid = str(parent.get('parent_gid') or '')
        elif parent.get('node_type') != 'station_process':
            invalid()
        station = source.get(station_gid)
        line = source.get(str((station or {}).get('parent_gid') or ''))
        if (not station or station.get('node_type') != 'station_process' or station.get('level') != 2
                or not line or line.get('node_type') != 'line_process'): invalid()
        target, clone_station = mapping.get(parent_gid), mapping.get(station_gid)
        if not target or not clone_station or clone[clone_station].get('level') != 2: invalid()
        if parent.get('node_type') == 'operator_process' and clone[target].get('level') != 3: invalid()
        code = process_to_code.get(gid)
        if code is not None:
            if code_station[code] != clone_station: invalid()
        else:
            code = 'DEMO-P-' + gid
            if code in plan['process_codes']: invalid()
            plan['process_codes'][code] = gid
            plan['station_codes'].setdefault(clone_station, []).append(code)
        targets[code] = target
    plan['process_target_parents'] = targets
    return plan


def _relation_plan(cur: Any, bop_gid: str, clone_info: dict | None = None) -> dict:
    cur.execute("SELECT gid,project_gid,meta FROM workmanship_bop_bop_versions WHERE gid=%s AND is_deleted=FALSE", (bop_gid,))
    row = cur.fetchone()
    meta = _parse_json((row or {}).get('meta'), {})
    demo = meta.get('demo') if isinstance(meta, dict) else None
    plan = demo.get('relation_plan') if isinstance(demo, dict) else None
    if plan is not None and not isinstance(plan, dict):
        raise CapabilityBusinessError('demo_relation_plan_invalid', '演示关系配置无效')
    source_gid = demo.get('source_version_gid') if isinstance(demo, dict) else None
    if source_gid:
        cur.execute("SELECT gid,project_gid FROM workmanship_bop_bop_versions WHERE gid=%s AND is_deleted=FALSE", (source_gid,))
        source_version = cur.fetchone()
        if (not source_version or not isinstance(demo, dict) or not demo.get('relation_demo')
                or not row.get('project_gid') or row.get('project_gid') != source_version.get('project_gid')
                or str(row.get('gid') or '') == str(source_gid)
                or str(source_version.get('gid') or '') != str(source_gid)):
            raise CapabilityBusinessError('demo_relation_plan_invalid', '演示关系源版本不存在')
        if clone_info is None: clone_info, _ = _load_tree(cur, bop_gid)
        source_info, _ = _load_tree(cur, source_gid, True)
        return _canonical_relation_plan(row, source_version, list(clone_info.values()), list(source_info.values()))
    return plan or {}


def _station_exts(cur: Any, station_entities: dict, bop_gid: str | None = None, plan: dict | None = None) -> dict:
    """entry_gid -> demo_process_codes list（一次批量查询）。"""
    if plan is None: plan = _relation_plan(cur, bop_gid) if bop_gid else {}
    if plan:
        return plan.get('station_codes') or {}
    entity_to_entry = {entity: entry for entry, entity in station_entities.items()}
    if not entity_to_entry:
        return {}
    result: dict = {}
    entities = list(entity_to_entry.keys())
    for i in range(0, len(entities), _FLUSH_CHUNK):
        chunk = entities[i:i + _FLUSH_CHUNK]
        placeholders = ",".join(["%s"] * len(chunk))
        cur.execute(
            f"SELECT gid, ext FROM workmanship_bop_bop_station WHERE gid IN ({placeholders}) AND is_deleted=FALSE",
            chunk,
        )
        for row in cur.fetchall():
            ext = _parse_json(row.get("ext"), {})
            codes = ext.get("demo_process_codes") if isinstance(ext, dict) else None
            entry_gid = entity_to_entry.get(row["gid"])
            if entry_gid and isinstance(codes, list) and codes:
                result[entry_gid] = [str(c) for c in codes]
    return result


def _steps_exts(cur: Any, steps_entities: dict, bop_gid: str | None = None, plan: dict | None = None) -> dict:
    """op entry_gid -> demo_part_codes list（一次批量查询）。"""
    if plan is None: plan = _relation_plan(cur, bop_gid) if bop_gid else {}
    if plan:
        return plan.get('operation_part_codes') or {}
    entity_to_entry = {entity: entry for entry, entity in steps_entities.items()}
    if not entity_to_entry:
        return {}
    result: dict = {}
    entities = list(entity_to_entry.keys())
    for i in range(0, len(entities), _FLUSH_CHUNK):
        chunk = entities[i:i + _FLUSH_CHUNK]
        placeholders = ",".join(["%s"] * len(chunk))
        cur.execute(
            f"SELECT gid, ext FROM workmanship_bop_bop_steps WHERE gid IN ({placeholders}) AND is_deleted=FALSE",
            chunk,
        )
        for row in cur.fetchall():
            ext = _parse_json(row.get("ext"), {})
            codes = ext.get("demo_part_codes") if isinstance(ext, dict) else None
            entry_gid = entity_to_entry.get(row["gid"])
            if entry_gid and isinstance(codes, list) and codes:
                result[entry_gid] = [str(c) for c in codes]
    return result


def _resolve_line(info: dict, children: dict, holding_gid: str, station_codes: dict, line_gid: str | None) -> str:
    lines = [g for g, e in info.items() if e["node_type"] == "line_process" and g != holding_gid]
    if line_gid:
        if line_gid not in lines:
            raise CapabilityBusinessError("demo_line_not_found", f"线体 {line_gid} 不在演示版本中")
        return line_gid
    # 默认取含演示编码工位最多的线体
    best, best_count = None, 0
    for gid in lines:
        count = sum(1 for child in children.get(gid, []) if child in station_codes)
        if count > best_count:
            best, best_count = gid, count
    if not best:
        raise CapabilityBusinessError("demo_line_not_found", "演示版本中没有带演示编码的线体")
    return best


def _pbom_by_demo_code(cur: Any, bop_gid: str, plan: dict | None = None) -> dict:
    if plan is None: plan = _relation_plan(cur, bop_gid)
    cur.execute(
        "SELECT p.gid, p.title, p.part_no, "
        "JSON_UNQUOTE(JSON_EXTRACT(p.meta,'$.demo_code')) AS demo_code "
        "FROM workmanship_bop_pbom p "
        "JOIN workmanship_bop_bop_versions v ON v.pbom_version_gid=p.snapshot_gid "
        "WHERE v.gid=%s AND p.is_deleted=FALSE",
        (bop_gid,),
    )
    rows = {str(row['gid']): dict(row) for row in cur.fetchall()}
    if plan:
        return {code: rows[str(gid)] for code, gid in (plan.get('pbom_codes') or {}).items() if str(gid) in rows}
    return {row['demo_code']: row for row in rows.values() if row.get('demo_code')}


def _process_by_code(cur: Any, bop_gid: str, plan: dict | None = None) -> dict:
    if plan is None: plan = _relation_plan(cur, bop_gid)
    if plan:
        return plan.get('process_codes') or {}
    cur.execute(
        "SELECT l.entry_gid, p.process_code FROM workmanship_bop_bop_process p "
        "JOIN workmanship_bop_bop_entry_links l ON l.entity_gid=p.gid AND l.link_type='bop_process' AND l.is_deleted=FALSE "
        "JOIN workmanship_bop_bop_entries e ON e.gid=l.entry_gid AND e.is_deleted=FALSE "
        "WHERE e.version_gid=%s AND p.process_code LIKE %s",
        (bop_gid, DEMO_CODE_PREFIX + "%"),
    )
    return {row["process_code"]: row["entry_gid"] for row in cur.fetchall()}


def _existing_operation_part_links(cur: Any, bop_gid: str, operation_gids: list[str] | None = None) -> dict:
    # Keep legacy callers unchanged; Connect needs only its selected operations.
    selected = list(dict.fromkeys(operation_gids)) if operation_gids is not None else None
    chunks = [None] if selected is None else [selected[i:i + _FLUSH_CHUNK] for i in range(0, len(selected), _FLUSH_CHUNK)]
    result = {}
    for chunk in chunks:
        scope_sql = '' if chunk is None else ' AND e.gid IN (' + ','.join(['%s'] * len(chunk)) + ')'
        params = (bop_gid,) if chunk is None else (bop_gid, *chunk)
        cur.execute("SELECT l.gid,l.entry_gid,l.entity_gid,l.is_deleted FROM workmanship_bop_bop_entry_links l "
            "JOIN workmanship_bop_bop_entries e ON e.gid=l.entry_gid "
            "WHERE e.version_gid=%s AND e.node_type='operation' AND e.is_deleted=FALSE "
            "AND l.link_type='pbom_part'" + scope_sql + " ORDER BY l.is_deleted,l.gid", params)
        for row in cur.fetchall():
            result.setdefault((str(row['entry_gid']), str(row['entity_gid'])), dict(row))
    return result


def _insert_part_links(cur: Any, rows: list) -> None:
    # PyMySQL cannot batch this VALUES expression (NOW and fixed literals).
    # Use one parameterized statement per bounded chunk in the same transaction.
    for offset in range(0, len(rows), _FLUSH_CHUNK):
        chunk = rows[offset:offset + _FLUSH_CHUNK]
        cur.execute(
            "INSERT INTO workmanship_bop_bop_entry_links "
            "(gid,entry_gid,link_type,entity_gid,is_primary,is_inherited,snapshot_data,version_gid,created_at) VALUES "
            + ','.join(["(%s,%s,'pbom_part',%s,FALSE,FALSE,%s,%s,NOW(6))"] * len(chunk)),
            [value for row in chunk for value in row],
        )


def _connect(cur: Any, bop_gid: str, line_gid: str | None) -> dict:
    from backend.platform_sdk.ids import next_gid

    info, children = _phase_call(cur, 'tree', _load_tree, cur, bop_gid)
    plan = _phase_call(cur, 'canonical_plan', _relation_plan, cur, bop_gid, info)
    holding_gid = _phase_call(cur, 'holding', _holding_line, cur, bop_gid, info)
    stations = {} if plan else _phase_call(cur, 'station_links', _entity_links, cur, bop_gid, "bop_station")
    station_codes = _phase_call(cur, 'station_codes', _station_exts, cur, stations, bop_gid, plan)
    operations = {} if plan else _phase_call(cur, 'step_links', _entity_links, cur, bop_gid, "bop_steps")
    steps_codes = _phase_call(cur, 'step_codes', _steps_exts, cur, operations, bop_gid, plan)
    code_to_entry = _phase_call(cur, 'process_codes', _process_by_code, cur, bop_gid, plan)
    pbom_by_code = _phase_call(cur, 'pbom', _pbom_by_demo_code, cur, bop_gid, plan)
    target_line = _resolve_line(info, children, holding_gid, station_codes, line_gid)
    station_gids = [g for g in children.get(target_line, []) if info[g]["node_type"] == "station_process" and (info[g].get("level") or 0) == 2]
    selected_operations = [op for station in station_gids for code in station_codes.get(station) or []
        if code_to_entry.get(code) for op in children.get(code_to_entry[code], []) if info[op]['node_type'] == 'operation']
    existing_parts = _phase_call(cur, 'existing_links', _existing_operation_part_links, cur, bop_gid, selected_operations)
    restore_parts, insert_parts = [], []
    link_snapshot = json.dumps({"demo": DEMO_LINK_TAG})

    planner = _MovePlanner(info, children)
    steps: list = []
    processes_moved = 0
    operations_touched = 0
    part_links = 0
    with _diagnostic_phase(cur, 'planning'):
        for station_entry_gid in station_gids:
            codes = station_codes.get(station_entry_gid) or []
            if not codes:
                continue
            station_step = {"station_gid": station_entry_gid, "station_title": info[station_entry_gid].get("title") or "", "processes": []}
            for code in codes:
                proc_entry_gid = code_to_entry.get(code)
                if not proc_entry_gid:
                    continue
                proc = info[proc_entry_gid]
                target_parent = (plan.get('process_target_parents') or {}).get(code, station_entry_gid)
                already_in_place = proc.get("parent_gid") == target_parent
                if not already_in_place:
                    planner.move(proc_entry_gid, target_parent)
                    processes_moved += 1
                proc_step = {"entry_gid": proc_entry_gid, "title": proc.get("title") or "", "process_code": code, "operations": []}
                for op_gid in [g for g in children.get(proc_entry_gid, []) if info[g]["node_type"] == "operation"]:
                    operations_touched += 1
                    part_entries = [g for g in _descendants(children, op_gid) if info[g]["node_type"] in PART_NODE_TYPES]
                    op_step = {"entry_gid": op_gid, "title": info[op_gid].get("title") or "",
                               "parts": [{"entry_gid": g, "title": info[g].get("title") or ""} for g in part_entries]}
                    for part_code in steps_codes.get(op_gid) or []:
                        pbom = pbom_by_code.get(part_code)
                        if not pbom:
                            continue  # 无匹配零件，跳过
                        pair = (str(op_gid), str(pbom['gid']))
                        existing = existing_parts.get(pair)
                        if existing and not existing["is_deleted"]:
                            continue  # 幂等：关系已存在
                        if existing:
                            restore_parts.append(existing['gid'])
                        else:
                            insert_parts.append((str(next_gid()), op_gid, pbom['gid'], link_snapshot, bop_gid))
                        existing_parts[pair] = {'is_deleted': False}
                        part_links += 1
                    proc_step["operations"].append(op_step)
                station_step["processes"].append(proc_step)
            if station_step["processes"]:
                steps.append(station_step)
    with _diagnostic_phase(cur, 'restore_links'):
        for offset in range(0, len(restore_parts), _FLUSH_CHUNK):
            chunk = restore_parts[offset:offset + _FLUSH_CHUNK]
            cur.execute("UPDATE workmanship_bop_bop_entry_links SET is_deleted=FALSE,deleted_at=NULL,snapshot_data=%s "
                "WHERE version_gid=%s AND gid IN (" + ','.join(['%s'] * len(chunk)) + ')',
                [link_snapshot, bop_gid, *chunk])
    with _diagnostic_phase(cur, 'insert_links'):
        _insert_part_links(cur, insert_parts)
    _phase_call(cur, 'move_flush', planner.flush, cur)
    return {
        "ok": True,
        "operation": "connect",
        "line_gid": target_line,
        "line_title": info[target_line].get("title") or "",
        "stations": len(steps),
        "processes_moved": processes_moved,
        "operations": operations_touched,
        "part_links": part_links,
        "steps": steps,
    }


def _reset(cur: Any, bop_gid: str, line_gid: str | None) -> dict:
    info, children = _phase_call(cur, 'tree', _load_tree, cur, bop_gid)
    plan = _phase_call(cur, 'canonical_plan', _relation_plan, cur, bop_gid, info)
    holding_gid = _phase_call(cur, 'holding', _holding_line, cur, bop_gid, info)
    code_to_entry = _phase_call(cur, 'process_codes', _process_by_code, cur, bop_gid, plan)
    coded_entry_gids = set(code_to_entry.values())

    if line_gid:
        if line_gid not in info or info[line_gid]["node_type"] != "line_process":
            raise CapabilityBusinessError("demo_line_not_found", f"线体 {line_gid} 不在演示版本中")
        scope_stations = {g for g in children.get(line_gid, []) if info[g]["node_type"] == "station_process"}
    else:
        scope_stations = {g for g, e in info.items() if e["node_type"] == "station_process"}
    if plan.get('process_target_parents'):
        scoped_codes = {code for station, codes in plan['station_codes'].items() if station in scope_stations for code in codes}
        movable = [code_to_entry[code] for code in scoped_codes
                   if info[code_to_entry[code]].get('parent_gid') == plan['process_target_parents'][code]]
    else:
        movable = [g for g in coded_entry_gids if info[g].get("parent_gid") in scope_stations]

    op_gids: list = []
    for entry_gid in movable:
        for descendant in _descendants(children, entry_gid):
            if info[descendant]["node_type"] == "operation":
                op_gids.append(descendant)

    with _diagnostic_phase(cur, 'remove_links'):
        part_links_removed = 0
        for i in range(0, len(op_gids), _FLUSH_CHUNK):
            chunk = op_gids[i:i + _FLUSH_CHUNK]
            placeholders = ",".join(["%s"] * len(chunk))
            cur.execute(
                "UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE, deleted_at=NOW(6) "
                f"WHERE entry_gid IN ({placeholders}) AND link_type='pbom_part' AND is_deleted=FALSE "
                "AND JSON_UNQUOTE(JSON_EXTRACT(snapshot_data,'$.demo'))=%s",
                (*chunk, DEMO_LINK_TAG),
            )
            if cur.rowcount and cur.rowcount > 0:
                part_links_removed += cur.rowcount

    planner = _MovePlanner(info, children)
    for entry_gid in movable:
        planner.move(entry_gid, holding_gid)
    _phase_call(cur, 'move_flush', planner.flush, cur)
    return {
        "ok": True,
        "operation": "reset",
        "line_gid": line_gid,
        "processes_moved": len(movable),
        "part_links_removed": part_links_removed,
    }


def _line_steps(info: dict, children: dict, station_codes: dict, code_to_entry: dict, line_gid: str, target_parents: dict | None = None) -> list:
    """按当前父子关系生成某条线体的完整演示 steps（含已就位的工序）。"""
    steps: list = []
    station_gids = [g for g in children.get(line_gid, []) if info[g]["node_type"] == "station_process" and (info[g].get("level") or 0) == 2]
    for station_entry_gid in station_gids:
        codes = station_codes.get(station_entry_gid) or []
        if not codes:
            continue
        station_step = {"station_gid": station_entry_gid, "station_title": info[station_entry_gid].get("title") or "", "processes": []}
        for code in codes:
            proc_entry_gid = code_to_entry.get(code)
            if not proc_entry_gid:
                continue
            if info[proc_entry_gid].get("parent_gid") != (target_parents or {}).get(code, station_entry_gid):
                continue  # 仍在待连接区，未连接
            proc_step = {"entry_gid": proc_entry_gid, "title": info[proc_entry_gid].get("title") or "", "process_code": code, "operations": []}
            for op_gid in [g for g in children.get(proc_entry_gid, []) if info[g]["node_type"] == "operation"]:
                part_entries = [g for g in _descendants(children, op_gid) if info[g]["node_type"] in PART_NODE_TYPES]
                proc_step["operations"].append({
                    "entry_gid": op_gid, "title": info[op_gid].get("title") or "",
                    "parts": [{"entry_gid": g, "title": info[g].get("title") or ""} for g in part_entries],
                })
            station_step["processes"].append(proc_step)
        if station_step["processes"]:
            steps.append(station_step)
    return steps


def _status(cur: Any, bop_gid: str) -> dict:
    """只读：返回每条线体的演示连接状态及已连接线体的完整 steps。"""
    info, children = _load_tree(cur, bop_gid)
    plan = _phase_call(cur, 'canonical_plan', _relation_plan, cur, bop_gid, info)
    holding_gid = _holding_line(cur, bop_gid, info)
    stations = {} if plan else _entity_links(cur, bop_gid, "bop_station")
    station_codes = _station_exts(cur, stations, bop_gid, plan)
    code_to_entry = _process_by_code(cur, bop_gid, plan)
    lines: list = []
    root_children = [g for g, e in info.items() if e["node_type"] == "line_process" and not (e.get("parent_gid"))]
    for line in sorted(root_children, key=lambda g: (info[g].get("sort_order") or 0)):
        if line == holding_gid:
            continue
        steps = _line_steps(info, children, station_codes, code_to_entry, line, plan.get('process_target_parents'))
        connected = sum(len(st["processes"]) for st in steps)
        lines.append({
            "line_gid": line,
            "line_title": info[line].get("title") or "",
            "connected": connected > 0,
            "processes_connected": connected,
            "steps": steps,
        })
    return {"ok": True, "operation": "status", "processes_moved": 0, "lines": lines}


@transactional_provider
def apply_demo_relation_change(payload: dict[str, Any], context: CapabilityContext):
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    _require_super_admin(context)
    bop_gid = str(payload.get("bop_gid") or "").strip()
    if not bop_gid:
        raise ValueError("bop_gid is required")
    line_gid = str(payload.get("line_gid") or "").strip() or None

    from ..data.connection import get_conn, open_craft_transaction

    if operation == "status":
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur = _diagnostic_cursor(cur)
                _phase_call(cur, 'version_auth', _require_demo_version, cur, bop_gid, context)
                return {"data": _phase_call(cur, 'status_total', _status, cur, bop_gid)}
    conn = open_craft_transaction()
    try:
        with conn.cursor() as cur:
            cur = _diagnostic_cursor(cur)
            _phase_call(cur, 'version_auth', _require_demo_version, cur, bop_gid, context)
            data = _phase_call(cur, 'connect_total' if operation == "connect" else 'reset_total', _connect if operation == "connect" else _reset, cur, bop_gid, line_gid)
        return TransactionalCapabilityOutput(data={"data": data}, transaction=conn)
    except BaseException:
        try: conn.rollback()
        finally: conn.close()
        raise


def register_demo_relation_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.demo.relation.change.apply", owner="craft",
        description="Connect or reset demo station/process/operation/part relations by hidden codes inside a marked demo BOP version.",
        use_when="A super_admin runs the process-relation demo, or the server-configured test demo actor runs it on a marked L5 BOP version.",
        do_not_use_when="The target BOP version is unmarked, or the caller lacks server-configured demo access to that project.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "bop_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "bop", "demo", "relation", "write"),
    ), apply_demo_relation_change)


__all__ = ["OPERATIONS", "apply_demo_relation_change", "register_demo_relation_change_capability"]
