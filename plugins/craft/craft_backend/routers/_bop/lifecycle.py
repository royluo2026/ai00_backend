"""
backend/routers/_bop/lifecycle.py
──────────────────────────────────
BOP 生命周期面板 API：阶段推进、完善度指标、Checkpoint、操作日志。
"""
import json
from typing import Optional, List
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ...data.connection import get_conn
from backend.platform_sdk.ids import next_gid
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility

from ._constants import _WRITE, _READ
from . import _history

router = APIRouter(prefix="/api/bop", tags=["bop"])

_NEXT_PHASE = {
    'init': 'refine',
    'refine': 'publish_cycle',
    'publish_cycle': 'archived',
}


async def _invoke_lifecycle_read(request, current_user, principal, gateway, capability_id, operation, gid, *, line_gid=None, limit=50):
    payload = {"operation": operation, "gid": gid, "limit": limit}
    if line_gid:
        payload["line_gid"] = line_gid
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload=payload, current_user=current_user, principal=principal,
        request_id=request.headers.get("X-Request-ID") or f"craft_bop_lifecycle_legacy_{next_gid()}", trace_id=request.headers.get("X-Trace-ID") or "craft_bop_lifecycle",
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"invalid_input": 400, "permission_denied": 403, "resource_not_found": 404}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data


async def _invoke_lifecycle_change(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_lifecycle_change_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.change.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400, "response_limit_exceeded": 413, "confirmation_required": 409}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


async def _invoke_lifecycle_state_change(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_lifecycle_state_change_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.state.change.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400, "invalid_state": 409}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


async def _invoke_checkpoint_change(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_checkpoint_change_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.checkpoint.change.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


async def _invoke_checkpoint_rollback(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_checkpoint_rollback_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.checkpoint.rollback.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400, "invalid_state": 409}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


async def _invoke_lifecycle_history_change(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_lifecycle_history_change_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.history.change.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400, "invalid_state": 409}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


async def _invoke_lifecycle_step_rollback(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_lifecycle_step_rollback_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.step.rollback.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


async def _invoke_lifecycle_stats_refresh(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_lifecycle_stats_refresh_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.stats.refresh.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


# ─── Pydantic 模型 ────────────────────────────────────────────────────────────

class ConfirmPhaseBody(BaseModel):
    note: Optional[str] = None


class CheckpointBody(BaseModel):
    label: Optional[str] = None


class UndoStepBody(BaseModel):
    step_key: str
    pbom_version_gid: Optional[str] = None   # vpps_imported 步骤需要传入


class InitStateBody(BaseModel):
    route:     Optional[str]  = None   # blank|from_template|from_existing|tc_import
    checklist: Optional[dict] = None   # {step_key: True/False}


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _get_line_subtree_gids(cur, version_gid: str, line_gid: str) -> List[str]:
    """递归获取某条线体下所有 bop_entries 的 gid（包含线体自身）"""
    cur.execute("""
        WITH RECURSIVE subtree AS (
            SELECT gid FROM workmanship_bop_bop_entries
            WHERE gid = %s AND version_gid = %s AND is_deleted = FALSE
            UNION ALL
            SELECT e.gid FROM workmanship_bop_bop_entries e
            JOIN subtree s ON e.parent_gid = s.gid
            WHERE e.version_gid = %s AND e.is_deleted = FALSE
        )
        SELECT gid FROM subtree
    """, (line_gid, version_gid, version_gid))
    return [r['gid'] for r in cur.fetchall()]


def _get_family_phase(cur, family_gid: str) -> str:
    """读取族群级 lifecycle_phase（表不存在时静默返回空串）"""
    if not family_gid:
        return ''
    try:
        cur.execute(
            "SELECT lifecycle_phase FROM workmanship_bop_bop_version_families WHERE gid=%s",
            (family_gid,)
        )
        row = cur.fetchone()
        return (dict(row) or {}).get('lifecycle_phase', '') if row else ''
    except Exception:
        return ''


def _get_diff_queue_count(cur, version_gid: str) -> int:
    """读取 PBOM 差异工作队列中 pending 条数（表不存在时返回 0）"""
    try:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM workmanship_bop_bop_pbom_diff_queue "
            "WHERE bop_version_gid=%s AND status='pending'",
            (version_gid,)
        )
        row = cur.fetchone()
        return (dict(row) or {}).get('cnt', 0) if row else 0
    except Exception:
        return 0


def _compute_stats(cur, version_gid: str, line_gid: Optional[str]) -> dict:
    """
    计算一个版本（或某条线体）的完善度指标。
    NOK vpps / unbound_parts / unbound_ops / coverage_ok / balance_ok 为 Phase B 实现，暂返回 0/False。
    """
    empty = {
        'nok_vpps': 0, 'nok_unbound_parts': 0, 'nok_unbound_ops': 0,
        'tools_bound': 0, 'tools_total': 0,
        'fixtures_bound': 0, 'fixtures_total': 0,
        'equipment_bound': 0, 'equipment_total': 0,
        'coverage_ok': False, 'balance_ok': False,
        'tasks_done': 0, 'tasks_total': 0,
        'issues_open': 0, 'rules_warn': 0, 'rules_block': 0,
        'deliverable_bound': 0, 'deliverable_total': 0,
    }

    if line_gid:
        scope_gids = _get_line_subtree_gids(cur, version_gid, line_gid)
        if not scope_gids:
            return empty
        ph = ','.join(['%s'] * len(scope_gids))
        entry_filter  = f"e.version_gid = %s AND e.gid IN ({ph}) AND e.is_deleted = FALSE"
        entry_params  = [version_gid] + scope_gids
        # bop_entry_links 过滤（使用 entry_gid）
        link_filter   = f"e.version_gid = %s AND e.gid IN ({ph}) AND e.is_deleted = FALSE"
        link_params   = [version_gid] + scope_gids
    else:
        entry_filter  = "e.version_gid = %s AND e.is_deleted = FALSE"
        entry_params  = [version_gid]
        link_filter   = "e.version_gid = %s AND e.is_deleted = FALSE"
        link_params   = [version_gid]

    # 工具需求绑定（tool_need → project_tools）
    cur.execute(f"""
        SELECT
          COUNT(*) AS total,
          COUNT(l.entity_gid) AS bound
        FROM workmanship_bop_bop_entries e
        LEFT JOIN workmanship_bop_bop_entry_links l
          ON l.entry_gid = e.gid AND l.link_type = 'project_tools' AND l.is_deleted = FALSE
        WHERE {entry_filter} AND e.node_type = 'tool_need'
    """, entry_params)
    r = cur.fetchone()
    tools_total, tools_bound = (r['total'], r['bound']) if r else (0, 0)

    # 工装需求绑定（fixture_need → project_tooling）
    cur.execute(f"""
        SELECT COUNT(*) AS total, COUNT(l.entity_gid) AS bound
        FROM workmanship_bop_bop_entries e
        LEFT JOIN workmanship_bop_bop_entry_links l
          ON l.entry_gid = e.gid AND l.link_type = 'project_tooling' AND l.is_deleted = FALSE
        WHERE {entry_filter} AND e.node_type = 'fixture_need'
    """, entry_params)
    r = cur.fetchone()
    fixtures_total, fixtures_bound = (r['total'], r['bound']) if r else (0, 0)

    # 设备需求绑定（equipment_need → project_equipment）
    cur.execute(f"""
        SELECT COUNT(*) AS total, COUNT(l.entity_gid) AS bound
        FROM workmanship_bop_bop_entries e
        LEFT JOIN workmanship_bop_bop_entry_links l
          ON l.entry_gid = e.gid AND l.link_type = 'project_equipment' AND l.is_deleted = FALSE
        WHERE {entry_filter} AND e.node_type = 'equipment_need'
    """, entry_params)
    r = cur.fetchone()
    equipment_total, equipment_bound = (r['total'], r['bound']) if r else (0, 0)

    # Project task/issue state is cross-domain. This Craft-owned snapshot does
    # not infer it from Project tables; governed Project capabilities provide it.
    tasks_total = tasks_done = issues_open = 0

    # 工艺交付物完成度（有工艺卡/控制计划/人机姿态 link 的工序数）
    del_filter = "AND (l2.is_deleted IS NULL OR l2.is_deleted=FALSE)"
    cur.execute(f"""
        SELECT
          COUNT(DISTINCT e.gid) AS total,
          COUNT(DISTINCT CASE WHEN l2.entity_gid IS NOT NULL THEN e.gid END) AS bound
        FROM workmanship_bop_bop_entries e
        LEFT JOIN workmanship_bop_bop_entry_links l2
          ON l2.entry_gid = e.gid
         AND l2.link_type IN ('process_chart','control_plan','jack_pos')
         {del_filter}
        WHERE {entry_filter} AND e.node_type = 'asm_operation'
    """, entry_params)
    r = cur.fetchone()
    deliverable_total = r['total'] if r else 0
    deliverable_bound = r['bound'] if r else 0

    return {
        'nok_vpps': 0,           # Phase B
        'nok_unbound_parts': 0,  # Phase B
        'nok_unbound_ops': 0,    # Phase B
        'tools_bound': tools_bound,
        'tools_total': tools_total,
        'fixtures_bound': fixtures_bound,
        'fixtures_total': fixtures_total,
        'equipment_bound': equipment_bound,
        'equipment_total': equipment_total,
        'coverage_ok': False,    # Phase B
        'balance_ok': False,     # Phase B
        'tasks_done': tasks_done,
        'tasks_total': tasks_total,
        'issues_open': issues_open,
        'rules_warn': 0,         # Phase B
        'rules_block': 0,        # Phase B
        'deliverable_bound': deliverable_bound,
        'deliverable_total': deliverable_total,
    }


# ─── 端点 ─────────────────────────────────────────────────────────────────────

@router.patch("/versions/{gid}/lifecycle/init-state", status_code=200)
async def update_init_state(gid: str, body: InitStateBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_state_change(request, _u, principal, gateway, {"operation": "init.update", "version_gid": gid, **body.model_dump(exclude_unset=True)})


def _legacy_update_init_state(gid: str, body: InitStateBody, _u=Depends(_WRITE)):
    """更新 lifecycle_state.init：保存路线选择和步骤完成状态"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lifecycle_state FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"版本 {gid} 不存在")
            state = dict(row)['lifecycle_state'] or {}
            if isinstance(state, str):
                state = json.loads(state)

            init = state.get('init', {})
            # 用 model_fields_set 区分"字段未提供"与"字段显式设为 null"
            if 'route' in body.model_fields_set:
                if body.route is None:
                    init.pop('route', None)     # null = 清除路线
                else:
                    init['route'] = body.route
            if 'checklist' in body.model_fields_set and body.checklist is not None:
                if body.checklist:              # 非空 = 合并
                    init['checklist'] = {**(init.get('checklist') or {}), **body.checklist}
                else:                           # 空 dict = 重置
                    init['checklist'] = {}
            state['init'] = init

            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET lifecycle_state=%s, updated_at=NOW() WHERE gid=%s",
                (json.dumps(state), gid)
            )
            conn.commit()
            return {"lifecycle_state": state}


@router.get("/versions/{gid}/lifecycle")
async def get_lifecycle(gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    """返回当前阶段、lifecycle_state、全局 stats、各阶段历史、操作列表。"""
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.lifecycle.state.read", payload={"version_gid": gid}, current_user=_u,
        principal=principal, request_id=request.headers.get("X-Request-ID") or f"craft_bop_lifecycle_state_legacy_{next_gid()}", trace_id=request.headers.get("X-Trace-ID") or "craft_bop_lifecycle_state",
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"invalid_input": 400, "permission_denied": 403, "resource_not_found": 404}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data


def _legacy_get_lifecycle(gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lifecycle_phase, lifecycle_state, bop_name, version_tag, data_stage, version_family_gid "
                "FROM workmanship_bop_bop_versions WHERE gid=%s",
                (gid,)
            )
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, f"版本 {gid} 不存在")
            ver = dict(ver)
            family_gid = ver.get('version_family_gid') or gid

            cur.execute(
                "SELECT * FROM workmanship_bop_bop_lifecycle_stats "
                "WHERE version_gid=%s AND line_gid IS NULL "
                "ORDER BY stats_snapshot_date DESC, refreshed_at DESC LIMIT 1",
                (gid,)
            )
            stats_row = cur.fetchone()
            stats = dict(stats_row) if stats_row else None

            cur.execute("""
                SELECT * FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY line_gid
                        ORDER BY stats_snapshot_date DESC, refreshed_at DESC
                    ) AS _rn
                    FROM workmanship_bop_bop_lifecycle_stats
                    WHERE version_gid=%s AND line_gid IS NOT NULL
                ) _t WHERE _rn = 1
            """, (gid,))
            line_stats = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT * FROM workmanship_bop_bop_lifecycle_history "
                "WHERE version_gid=%s ORDER BY entered_at",
                (gid,)
            )
            history = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT gid, title FROM workmanship_bop_bop_entries "
                "WHERE version_gid=%s AND node_type='line_process' AND is_deleted=FALSE "
                "ORDER BY sort_order",
                (gid,)
            )
            lines = [dict(r) for r in cur.fetchall()]

            # ── 读取 PBOM 统计（从 meta 字段）────────────────────────────────
            cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            bop_meta_row = cur.fetchone()
            _raw = dict(bop_meta_row)['meta'] if bop_meta_row else None
            bop_meta = json.loads(_raw) if isinstance(_raw, str) else (_raw or {})
            pbom_match = bop_meta.get('pbom_match', {})
            pbom_vpps_check = {}
            pbom_ver_gid = pbom_match.get('pbom_version_gid', '')
            if pbom_ver_gid:
                cur.execute("SELECT meta FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_ver_gid,))
                prow = cur.fetchone()
                if prow:
                    _pm = dict(prow)['meta']
                    _pm = json.loads(_pm) if isinstance(_pm, str) else (_pm or {})
                    pbom_vpps_check = _pm.get('vpps_check', {})

            # lifecycle_state 在 DB 存为 TEXT/JSON，PyMySQL 可能返回字符串
            _ls = ver['lifecycle_state']
            if isinstance(_ls, str):
                try:
                    _ls = json.loads(_ls) if _ls else {}
                except Exception:
                    _ls = {}
            elif _ls is None:
                _ls = {}

            return {
                "lifecycle_phase":  ver['lifecycle_phase'],
                "lifecycle_state":  _ls,
                "bop_name":         ver['bop_name'],
                "version_tag":      ver['version_tag'],
                "data_stage":       ver['data_stage'],
                "version_family_gid": family_gid,
                "stats":            stats,
                "line_stats":       line_stats,
                "history":          history,
                "lines":            lines,
                "pbom_match":       pbom_match,
                "pbom_vpps_check":  pbom_vpps_check,
                "family_lifecycle_phase": _get_family_phase(cur, ver.get('version_family_gid', '')),
                "pbom_diff_queue_pending": _get_diff_queue_count(cur, gid),
                "vehicle_ops_prep": bop_meta.get('vehicle_ops_prep', {}),
                # 族内所有版本（含 active / baseline / M / archived），供前端"切片历史"等展示
                "all_versions_in_family": _list_family_versions(cur, family_gid),
            }



def _list_family_versions(cur, family_gid: str) -> list:
    """返回某版本族下所有版本（精简字段）"""
    try:
        cur.execute(
            "SELECT gid, version_tag, bop_name, version_family_gid, data_stage, "
            "       status, change_note, archived_at, frozen_at, published_at, is_deleted "
            "FROM workmanship_bop_bop_versions "
            "WHERE (version_family_gid=%s OR gid=%s) AND is_deleted=FALSE "
            "ORDER BY created_at",
            (family_gid, family_gid)
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


@router.post("/versions/{gid}/lifecycle/refresh-stats", status_code=202)
async def _refresh_stats_endpoint(gid: str, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_stats_refresh(request, _u, principal, gateway, {"version_gid": gid})


def _legacy_refresh_stats(gid: str, background_tasks: BackgroundTasks, _u=Depends(_WRITE)):
    """重新计算所有指标，写入今日快照行。后台执行，立即返回。"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    import threading

    def _compute_and_write():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
                if not cur.fetchone():
                    return

                cur.execute(
                    "SELECT gid FROM workmanship_bop_bop_entries "
                    "WHERE version_gid=%s AND node_type='line_process' AND is_deleted=FALSE",
                    (gid,)
                )
                line_gids = [r['gid'] for r in cur.fetchall()]

                today = date.today().isoformat()

                cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
                bop_meta_row = cur.fetchone()
                _raw = dict(bop_meta_row)['meta'] if bop_meta_row else None
                bop_meta = json.loads(_raw) if isinstance(_raw, str) else (_raw or {})
                pbom_ver_gid = bop_meta.get('pbom_match', {}).get('pbom_version_gid', '')
                vpps_nok_from_pbom = 0
                if pbom_ver_gid:
                    cur.execute("SELECT meta FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_ver_gid,))
                    prow = cur.fetchone()
                    if prow:
                        vpps_nok_from_pbom = (dict(prow)['meta'] or {}).get('vpps_check', {}).get('nok', 0) or 0

                for lg in [None] + line_gids:
                    s = _compute_stats(cur, gid, lg)
                    if lg is None and vpps_nok_from_pbom:
                        s['nok_vpps'] = vpps_nok_from_pbom
                    row_gid = str(next_gid())
                    vals = [
                        row_gid, gid, lg, today,
                        s['nok_vpps'], s['nok_unbound_parts'], s['nok_unbound_ops'],
                        s['tools_bound'], s['tools_total'],
                        s['fixtures_bound'], s['fixtures_total'],
                        s['equipment_bound'], s['equipment_total'],
                        s['coverage_ok'], s['balance_ok'],
                        s['tasks_done'], s['tasks_total'],
                        s['issues_open'], s['rules_warn'], s['rules_block'],
                        s['nok_vpps'], s['nok_unbound_parts'], s['nok_unbound_ops'],
                        s['tools_bound'], s['tools_total'],
                        s['fixtures_bound'], s['fixtures_total'],
                        s['equipment_bound'], s['equipment_total'],
                        s['coverage_ok'], s['balance_ok'],
                        s['tasks_done'], s['tasks_total'],
                        s['issues_open'], s['rules_warn'], s['rules_block'],
                    ]
                    cur.execute("""
                        INSERT INTO workmanship_bop_bop_lifecycle_stats
                          (gid, version_gid, line_gid, stats_snapshot_date,
                           nok_vpps, nok_unbound_parts, nok_unbound_ops,
                           tools_bound, tools_total, fixtures_bound, fixtures_total,
                           equipment_bound, equipment_total, coverage_ok, balance_ok,
                           tasks_done, tasks_total, issues_open, rules_warn, rules_block,
                           refreshed_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                        ON DUPLICATE KEY UPDATE
                          nok_vpps=VALUES(nok_vpps), nok_unbound_parts=VALUES(nok_unbound_parts),
                          nok_unbound_ops=VALUES(nok_unbound_ops),
                          tools_bound=VALUES(tools_bound), tools_total=VALUES(tools_total),
                          fixtures_bound=VALUES(fixtures_bound), fixtures_total=VALUES(fixtures_total),
                          equipment_bound=VALUES(equipment_bound), equipment_total=VALUES(equipment_total),
                          coverage_ok=VALUES(coverage_ok), balance_ok=VALUES(balance_ok),
                          tasks_done=VALUES(tasks_done), tasks_total=VALUES(tasks_total),
                          issues_open=VALUES(issues_open), rules_warn=VALUES(rules_warn),
                          rules_block=VALUES(rules_block), refreshed_at=NOW()
                    """, vals[:20])
                conn.commit()

    background_tasks.add_task(_compute_and_write)
    return {"accepted": True, "message": "refresh started", "version_gid": gid}


# Keep direct Python callers compatible while FastAPI uses the governed endpoint above.
refresh_stats = _legacy_refresh_stats


@router.get("/versions/{gid}/lifecycle/history")
async def get_lifecycle_history(gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_read(request, _u, principal, gateway, "craft.bop.lifecycle.read", "history", gid)


def _legacy_get_lifecycle_history(gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_bop_bop_lifecycle_history "
                "WHERE version_gid=%s ORDER BY entered_at",
                (gid,)
            )
            return {"data": [dict(r) for r in cur.fetchall()]}


@router.post("/versions/{gid}/lifecycle/confirm-phase", status_code=200)
async def confirm_phase(gid: str, body: ConfirmPhaseBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_state_change(request, _u, principal, gateway, {"operation": "phase.confirm", "version_gid": gid, **body.model_dump(exclude_unset=True)})


def _legacy_confirm_phase(gid: str, body: ConfirmPhaseBody, _u=Depends(_WRITE)):
    """PM 确认当前阶段完成，推进到下一阶段"""
    user_gid  = _u.get('gid')  if isinstance(_u, dict) else None
    user_name = _u.get('name') if isinstance(_u, dict) else None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lifecycle_phase FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,)
            )
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, f"版本 {gid} 不存在")

            current = dict(ver)['lifecycle_phase']
            if current not in _NEXT_PHASE:
                raise HTTPException(400, f"阶段 {current} 无法继续推进")

            next_phase = _NEXT_PHASE[current]

            cur.execute("""
                INSERT INTO workmanship_bop_bop_lifecycle_history
                  (gid, version_gid, phase, entered_at, confirmed_at,
                   confirmed_by_gid, confirmed_by_name, note)
                VALUES (%s,%s,%s,NOW(),NOW(),%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  confirmed_at=NOW(), confirmed_by_gid=%s,
                  confirmed_by_name=%s, note=%s
            """, [
                str(next_gid()), gid, current,
                user_gid, user_name, body.note,
                user_gid, user_name, body.note,
            ])

            cur.execute("""
                INSERT IGNORE INTO workmanship_bop_bop_lifecycle_history
                  (gid, version_gid, phase, entered_at)
                VALUES (%s,%s,%s,NOW())
            """, (str(next_gid()), gid, next_phase))

            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET lifecycle_phase=%s, updated_at=NOW() WHERE gid=%s",
                (next_phase, gid)
            )
            conn.commit()
            return {"lifecycle_phase": next_phase}


@router.get("/versions/{gid}/lifecycle/lines/{line_gid}/checkpoints")
async def list_checkpoints(gid: str, line_gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_read(request, _u, principal, gateway, "craft.bop.lifecycle.read", "checkpoints", gid, line_gid=line_gid)


def _legacy_list_checkpoints(gid: str, line_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, label, created_by, created_by_name, created_at "
                "FROM workmanship_bop_bop_line_checkpoints "
                "WHERE version_gid=%s AND line_gid=%s ORDER BY created_at DESC",
                (gid, line_gid)
            )
            return {"data": [dict(r) for r in cur.fetchall()]}


@router.post("/versions/{gid}/lifecycle/lines/{line_gid}/checkpoints", status_code=201)
async def create_checkpoint(gid: str, line_gid: str, body: CheckpointBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_checkpoint_change(request, _u, principal, gateway, {"operation": "create", "version_gid": gid, "line_gid": line_gid, **body.model_dump(exclude_unset=True)})


def _legacy_create_checkpoint(gid: str, line_gid: str, body: CheckpointBody, _u=Depends(_WRITE)):
    """为指定线体打快照"""
    user_gid  = _u.get('gid')  if isinstance(_u, dict) else None
    user_name = _u.get('name') if isinstance(_u, dict) else None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            if not cur.fetchone():
                raise HTTPException(404, f"版本 {gid} 不存在")

            scope_gids = _get_line_subtree_gids(cur, gid, line_gid)
            if not scope_gids:
                raise HTTPException(404, f"线体 {line_gid} 下无条目")

            ph = ','.join(['%s'] * len(scope_gids))
            cur.execute(
                f"SELECT * FROM workmanship_bop_bop_entries "
                f"WHERE gid IN ({ph}) AND is_deleted=FALSE",
                scope_gids
            )
            entries_snap = [dict(r) for r in cur.fetchall()]

            cur.execute(
                f"SELECT * FROM workmanship_bop_bop_entry_links "
                f"WHERE entry_gid IN ({ph}) AND is_deleted=FALSE",
                scope_gids
            )
            links_snap = [dict(r) for r in cur.fetchall()]

            ckpt_gid = str(next_gid())
            cur.execute("""
                INSERT INTO workmanship_bop_bop_line_checkpoints
                  (gid, version_gid, line_gid, label, created_by, created_by_name, snapshot)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                ckpt_gid, gid, line_gid, body.label,
                user_gid, user_name,
                json.dumps({'entries': entries_snap, 'links': links_snap}, default=str)
            ))
            conn.commit()
            return {"gid": ckpt_gid, "label": body.label}


@router.post(
    "/versions/{gid}/lifecycle/lines/{line_gid}/rollback/{checkpoint_gid}",
    status_code=200
)
async def rollback_to_checkpoint(
    gid: str, line_gid: str, checkpoint_gid: str, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)
):
    return await _invoke_checkpoint_rollback(request, _u, principal, gateway, {"version_gid": gid, "line_gid": line_gid, "checkpoint_gid": checkpoint_gid})


def _legacy_rollback_to_checkpoint(
    gid: str, line_gid: str, checkpoint_gid: str, _u=Depends(_WRITE)
):
    """将指定线体回滚到某个 Checkpoint 快照"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT snapshot FROM workmanship_bop_bop_line_checkpoints "
                "WHERE gid=%s AND version_gid=%s AND line_gid=%s",
                (checkpoint_gid, gid, line_gid)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Checkpoint 不存在")

            snap = dict(row)['snapshot']
            if isinstance(snap, str):
                snap = json.loads(snap)

            entries_snap = snap.get('entries', [])
            links_snap   = snap.get('links', [])

            # 软删除当前线体下所有 entries 和 links
            scope_gids = _get_line_subtree_gids(cur, gid, line_gid)
            if scope_gids:
                ph = ','.join(['%s'] * len(scope_gids))
                cur.execute(
                    f"UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW() "
                    f"WHERE gid IN ({ph})",
                    scope_gids
                )
                cur.execute(
                    f"UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE, deleted_at=NOW() "
                    f"WHERE entry_gid IN ({ph})",
                    scope_gids
                )

            # 恢复快照 entries（ON CONFLICT on PK gid）
            for e in entries_snap:
                row_dict = dict(e)
                cur.execute("""
                    INSERT INTO workmanship_bop_bop_entries
                      (gid, version_gid, parent_gid, node_type, sort_order, level,
                       ai00_level, title, vpps, vpps_desc, parent_bop_title,
                       child_vpps, owner_gid, meta, vpps_part, catia_occurrence_name, parent_vpps_name,
                       is_deleted, created_at, updated_at)
                    VALUES (%(gid)s,%(version_gid)s,%(parent_gid)s,%(node_type)s,
                            %(sort_order)s,%(level)s,%(ai00_level)s,%(title)s,%(vpps)s,
                            %(vpps_desc)s,%(parent_bop_title)s,%(child_vpps)s,
                            %(owner_gid)s,%(meta)s,'','','',FALSE,NOW(),NOW())
                    ON DUPLICATE KEY UPDATE
                      is_deleted=FALSE, deleted_at=NULL,
                      parent_gid=VALUES(parent_gid), sort_order=VALUES(sort_order),
                      title=VALUES(title), vpps=VALUES(vpps),
                      meta=VALUES(meta), updated_at=NOW()
                """, row_dict)

            # 恢复快照 links
            for lnk in links_snap:
                lnk_dict = dict(lnk)
                cur.execute("""
                    INSERT INTO workmanship_bop_bop_entry_links
                      (gid, entry_gid, version_gid, link_type, entity_gid,
                       is_primary, is_inherited, is_deleted)
                    VALUES (%(gid)s,%(entry_gid)s,%(version_gid)s,%(link_type)s,
                            %(entity_gid)s,%(is_primary)s,%(is_inherited)s,FALSE)
                    ON DUPLICATE KEY UPDATE
                      is_deleted=FALSE, deleted_at=NULL, updated_at=NOW()
                """, lnk_dict)

            conn.commit()
            return {
                "restored_entries": len(entries_snap),
                "restored_links":   len(links_snap),
            }




@router.get("/versions/{gid}/lifecycle/lines/{line_gid}/history")
async def get_line_history(
    gid: str,
    line_gid: str,
    request: Request,
    limit: int = Query(50, le=200),
    _u=Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_lifecycle_read(request, _u, principal, gateway, "craft.bop.lifecycle.read", "line_history", gid, line_gid=line_gid, limit=limit)


def _legacy_get_line_history(
    gid: str,
    line_gid: str,
    limit: int = Query(50, le=200),
    _u=Depends(_READ),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            history = _history.fetch_line_history(cur, gid, line_gid, limit)
            return {
                "data": history["items"],
                "latest_active_batch_id": history["latest_active_batch_id"],
            }




@router.post("/versions/{gid}/lifecycle/lines/{line_gid}/undo")
async def _undo_line_history_endpoint(
    gid: str,
    line_gid: str,
    request: Request,
    _u=Depends(_WRITE),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_lifecycle_history_change(request, _u, principal, gateway, {"operation": "undo", "version_gid": gid, "line_gid": line_gid})


def _legacy_undo_line_history(
    gid: str,
    line_gid: str,
    _u=Depends(_WRITE),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _history.ensure_history_schema(cur)
            cur.execute(_history.latest_active_batch_sql(), (gid, line_gid))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "没有可撤销的历史操作")
            batch_id = row['batch_id']
            events = _history.fetch_batch_events(cur, gid, line_gid, batch_id)
            if not events:
                raise HTTPException(404, "批次历史不存在")
            summary = []
            affected_entries = []
            for event in reversed(events):
                _history.apply_history_event(cur, event, direction="undo")
                op_type = event.get("op_type")
                entity_title = event.get("entity_title") or ""
                if op_type == "update_entry":
                    entity_title = event.get("entity_title") or ""
                elif op_type in ("create_entry", "delete_entry"):
                    entries = (event.get("old_state") or {}).get("entries", [])
                    for e in entries:
                        entity_title = e.get("title", entity_title)
                        affected_entries.append(e.get("gid"))
                affected_entries.append(event.get("entity_gid"))
                summary.append({
                    "op_type": op_type,
                    "entity_gid": event.get("entity_gid"),
                    "entity_title": entity_title,
                })
            _history.mark_batch_status(cur, gid, line_gid, batch_id, "undone", _u.get('gid', ''))
            # ── 查询刷新后的操作历史 ──
            history_data = _history.fetch_line_history(cur, gid, line_gid, limit=50)
            conn.commit()
            return {
                "batch_id": batch_id,
                "status": "undone",
                "version_gid": gid,
                "line_gid": line_gid,
                "summary": summary,
                "affected_entries": list({e for e in affected_entries if e}),
                "operation_log": history_data["items"],
                "latest_active_batch_id": history_data["latest_active_batch_id"],
            }


@router.post("/versions/{gid}/lifecycle/lines/{line_gid}/redo")
async def _redo_line_history_endpoint(
    gid: str,
    line_gid: str,
    request: Request,
    _u=Depends(_WRITE),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_lifecycle_history_change(request, _u, principal, gateway, {"operation": "redo", "version_gid": gid, "line_gid": line_gid})


def _legacy_redo_line_history(
    gid: str,
    line_gid: str,
    _u=Depends(_WRITE),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _history.ensure_history_schema(cur)
            cur.execute(_history.latest_undo_batch_sql(), (gid, line_gid))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "没有可重做的历史操作")
            batch_id = row['batch_id']
            events = _history.fetch_batch_events(cur, gid, line_gid, batch_id)
            if not events:
                raise HTTPException(404, "批次历史不存在")
            guard = None
            if events:
                guard = {"entries": []}
                for event in events:
                    if event.get('entity_gid'):
                        cur.execute("SELECT updated_at FROM workmanship_bop_bop_entries WHERE gid=%s", (event['entity_gid'],))
                        ts_row = cur.fetchone()
                        if ts_row:
                            guard["entries"].append({"gid": event['entity_gid'], "updated_at": ts_row.get('updated_at')})
            if not _history.validate_redo_guard(cur, guard):
                _history.mark_batch_status(cur, gid, line_gid, batch_id, "redo_invalidated", _u.get('gid', ''))
                conn.commit()
                raise HTTPException(409, "重做已失效：目标对象在撤销后已被修改")
            summary = []
            affected_entries = []
            for event in events:
                _history.apply_history_event(cur, event, direction="redo")
                op_type = event.get("op_type")
                entity_title = event.get("entity_title") or ""
                if op_type in ("create_entry", "delete_entry"):
                    entries = (event.get("new_state") or {}).get("entries", [])
                    for e in entries:
                        entity_title = e.get("title", entity_title)
                        affected_entries.append(e.get("gid"))
                affected_entries.append(event.get("entity_gid"))
                summary.append({
                    "op_type": op_type,
                    "entity_gid": event.get("entity_gid"),
                    "entity_title": entity_title,
                })
            _history.mark_batch_status(cur, gid, line_gid, batch_id, "active", _u.get('gid', ''))
            history_data = _history.fetch_line_history(cur, gid, line_gid, limit=50)
            conn.commit()
            return {
                "batch_id": batch_id,
                "status": "active",
                "version_gid": gid,
                "line_gid": line_gid,
                "summary": summary,
                "affected_entries": list({e for e in affected_entries if e}),
                "operation_log": history_data["items"],
                "latest_active_batch_id": history_data["latest_active_batch_id"],
            }


# Keep direct Python callers compatible while FastAPI uses the governed endpoints above.
undo_line_history = _legacy_undo_line_history
redo_line_history = _legacy_redo_line_history


@router.get("/versions/{gid}/lifecycle/lines/{line_gid}/operation-log")
async def get_operation_log(
    gid: str,
    line_gid: str,
    request: Request,
    limit: int = Query(50, le=200),
    _u=Depends(_READ),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    return await _invoke_lifecycle_read(request, _u, principal, gateway, "craft.bop.lifecycle.read", "operation_log", gid, line_gid=line_gid, limit=limit)


def _legacy_get_operation_log(
    gid: str,
    line_gid: str,
    limit: int = Query(50, le=200),
    _u=Depends(_READ),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _history.ensure_history_schema(cur)
            cur.execute("""
                SELECT gid, batch_id, op_type, entity_gid, entity_title,
                       op_seq, performed_by, performed_by_name, performed_at, rolled_back,
                       batch_status, undone_at, undone_by, redone_at, redone_by, invalidate_reason
                FROM workmanship_bop_bop_line_operation_log
                WHERE version_gid=%s AND line_gid=%s
                ORDER BY performed_at DESC, op_seq DESC
                LIMIT %s
            """, (gid, line_gid, limit))
            return {"data": [dict(r) for r in cur.fetchall()]}


# ─── 步骤撤销 ──────────────────────────────────────────────────────────────────

# 每个步骤软删的 bop_entry node_type 范围（递归删除子树）
_UNDO_STEP_NODE_TYPES = {
    'lines_added':    ['line_process'],
    'stations_added': ['asm_station_process', 'physical_station'],
    'processes_added': ['asm_operator_process', 'asm_operation', 'operator_process'],
}


@router.post("/versions/{gid}/lifecycle/undo-step", status_code=200)
async def _undo_lifecycle_step_endpoint(gid: str, body: UndoStepBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_step_rollback(request, _u, principal, gateway, {"version_gid": gid, **body.model_dump(exclude_unset=True)})


def _legacy_undo_lifecycle_step(gid: str, body: UndoStepBody, _u=Depends(_WRITE)):
    """
    撤销生命周期步骤：
    - lines_added / stations_added / processes_added：递归软删 bop_entries + 对应 bop_entry_links
    - vpps_imported：软删 bop_entry_links 中 link_type='pbom_part'（可按 pbom_version_gid 过滤）
    - pbom_vpps_checked：仅重置 checklist，无数据操作
    同时将 checklist[step_key] 置为 false。
    """
    step = body.step_key
    with get_conn() as conn:
        with conn.cursor() as cur:
            deleted_entries = 0
            deleted_links   = 0

            # 检查 bop_entry_links 是否有 is_deleted 列
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema='ai00' AND table_name='bop_entry_links'
                  AND column_name='is_deleted'
            """)
            _links_has_del = (cur.fetchone() or {}).get('count', 0) > 0

            def _soft_or_hard_links(where_sql, params):
                """软删或硬删 bop_entry_links，根据列是否存在决定。"""
                nonlocal deleted_links
                if _links_has_del:
                    cur.execute(
                        f"UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE WHERE {where_sql} AND is_deleted=FALSE",
                        params
                    )
                else:
                    cur.execute(
                        f"DELETE FROM workmanship_bop_bop_entry_links WHERE {where_sql}",
                        params
                    )
                deleted_links += cur.rowcount
                node_types = _UNDO_STEP_NODE_TYPES[step]
                placeholders = ','.join(['%s'] * len(node_types))

                # 递归软删 bop_entries（含子树）
                cur.execute(f"""
                    WITH RECURSIVE tree AS (
                        SELECT gid FROM workmanship_bop_bop_entries
                        WHERE version_gid = %s
                          AND node_type IN ({placeholders})
                          AND is_deleted = FALSE
                        UNION ALL
                        SELECT e.gid FROM workmanship_bop_bop_entries e
                        JOIN tree t ON e.parent_gid = t.gid
                        WHERE e.is_deleted = FALSE
                    )
                    UPDATE workmanship_bop_bop_entries SET is_deleted = TRUE
                    WHERE gid IN (SELECT gid FROM tree)
                """, [gid] + node_types)
                deleted_entry_gids = []
                deleted_entries = cur.rowcount

            if step in _UNDO_STEP_NODE_TYPES:
                node_types = _UNDO_STEP_NODE_TYPES[step]
                placeholders = ','.join(['%s'] * len(node_types))

                # 递归软删 bop_entries（含子树）
                cur.execute(f"""
                    WITH RECURSIVE tree AS (
                        SELECT gid FROM workmanship_bop_bop_entries
                        WHERE version_gid = %s
                          AND node_type IN ({placeholders})
                          AND is_deleted = FALSE
                        UNION ALL
                        SELECT e.gid FROM workmanship_bop_bop_entries e
                        JOIN tree t ON e.parent_gid = t.gid
                        WHERE e.is_deleted = FALSE
                    )
                    UPDATE workmanship_bop_bop_entries SET is_deleted = TRUE
                    WHERE gid IN (SELECT gid FROM tree)
                """, [gid] + node_types)
                deleted_entry_gids = []
                deleted_entries = cur.rowcount

                if deleted_entry_gids:
                    _ph = ",".join(["%s"] * len(deleted_entry_gids))
                    _soft_or_hard_links(
                        f"bop_entry_gid IN ({_ph})",
                        tuple(deleted_entry_gids)
                    )

            elif step == 'vpps_imported':
                if body.pbom_version_gid:
                    _soft_or_hard_links(
                        "version_gid=%s AND link_type='pbom_part' AND ref_gid IN (SELECT gid FROM workmanship_bop_pbom WHERE snapshot_gid=%s)",
                        (gid, body.pbom_version_gid)
                    )
                else:
                    _soft_or_hard_links(
                        "version_gid=%s AND link_type='pbom_part'",
                        (gid,)
                    )

            # 重置 lifecycle_state.init.checklist[step_key] = false
            cur.execute(
                "SELECT lifecycle_state FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"版本 {gid} 不存在")
            state = dict(row)['lifecycle_state'] or {}
            init  = state.get('init', {})
            cl    = init.get('checklist', {})
            cl[step] = False
            init['checklist'] = cl
            state['init'] = init
            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET lifecycle_state=%s, updated_at=NOW() WHERE gid=%s",
                (json.dumps(state), gid)
            )
            conn.commit()

            return {
                "step_key":       step,
                "deleted_entries": deleted_entries,
                "deleted_links":   deleted_links,
            }


# Keep direct Python callers compatible while FastAPI uses the governed endpoint above.
undo_lifecycle_step = _legacy_undo_lifecycle_step


# ─── PBOM-BOP 连接统计 ────────────────────────────────────────────────────────

@router.get("/versions/{gid}/pbom-link-stats", status_code=200)
async def get_pbom_link_stats(gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    """
    返回当前 BOP 版本中 PBOM 零件的链接统计：
      linked     - 已通过 bop_entry_links(link_type='pbom_part') 关联的 PBOM 部件数
      total      - 关联 PBOM 版本中的零件总数（从 pbom_version_gid 读取）
      pbom_version_gid - BOP 版本 meta.pbom_match.pbom_version_gid（上次关联的 PBOM 版本）
    """
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.pbom_lifecycle.read", payload={"operation": "link_stats", "gid": gid}, current_user=_u,
        principal=principal, request_id=request.headers.get("X-Request-ID") or f"craft_bop_pbom_link_stats_legacy_{next_gid()}", trace_id=request.headers.get("X-Trace-ID") or "craft_bop_pbom_link_stats",
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"invalid_input": 400, "permission_denied": 403, "resource_not_found": 404}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data


def _legacy_get_pbom_link_stats(gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 从 bop_versions.meta 拿上次记录的 pbom_version_gid
            cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "BOP版本不存在")
            meta = dict(row)['meta'] or {}
            pbom_ver_gid = meta.get('pbom_match', {}).get('pbom_version_gid', '')

            # 2. 已关联数：检查 is_deleted 列是否存在再过滤
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema='ai00' AND table_name='bop_entry_links'
                  AND column_name='is_deleted'
            """)
            has_is_deleted = (cur.fetchone() or {}).get('count', 0) > 0

            link_sql = """
                SELECT COUNT(DISTINCT ref_gid) AS linked
                FROM workmanship_bop_bop_entry_links
                WHERE version_gid=%s AND link_type='pbom_part'
            """ + (" AND is_deleted=FALSE" if has_is_deleted else "")
            cur.execute(link_sql, (gid,))
            linked = (cur.fetchone() or {}).get('linked', 0) or 0

            # 3. PBOM 总数
            total = 0
            if pbom_ver_gid:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM workmanship_bop_pbom WHERE snapshot_gid=%s",
                    (pbom_ver_gid,)
                )
                total = (cur.fetchone() or {}).get('cnt', 0) or 0

            return {
                "linked":          linked,
                "total":           total,
                "pbom_version_gid": pbom_ver_gid,
            }


class PbomMatchBody(BaseModel):
    pbom_version_gid:   str
    unlinked_ignored:   int = 0


class VehicleOpsStatsBody(BaseModel):
    confirmed: int = 0
    skipped:   int = 0
    total:     int = 0


@router.patch("/versions/{gid}/pbom-match", status_code=200)
async def patch_pbom_match(gid: str, body: PbomMatchBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_change(request, _u, principal, gateway, {"operation": "pbom_match.update", "version_gid": gid, **body.model_dump()})


def _legacy_patch_pbom_match(gid: str, body: PbomMatchBody, _u=Depends(_WRITE)):
    """将 PBOM 连接元数据写入 bop_versions.meta.pbom_match。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "BOP版本不存在")
            meta = dict(row)['meta'] or {}
            meta['pbom_match'] = {
                'pbom_version_gid': body.pbom_version_gid,
                'unlinked_ignored': body.unlinked_ignored,
            }
            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET meta=%s, updated_at=NOW() WHERE gid=%s",
                (json.dumps(meta), gid)
            )
            conn.commit()
    return {"success": True}


@router.patch("/versions/{gid}/vehicle-ops-stats", status_code=200)
async def patch_vehicle_ops_stats(gid: str, body: VehicleOpsStatsBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_change(request, _u, principal, gateway, {"operation": "vehicle_ops_stats.update", "version_gid": gid, **body.model_dump()})


def _legacy_patch_vehicle_ops_stats(gid: str, body: VehicleOpsStatsBody, _u=Depends(_WRITE)):
    """将车型工序准备统计写入 bop_versions.meta.vehicle_ops_prep。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "BOP版本不存在")
            meta = dict(row)['meta'] or {}
            meta['vehicle_ops_prep'] = {
                'confirmed': body.confirmed,
                'skipped':   body.skipped,
                'total':     body.total,
            }
            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET meta=%s, updated_at=NOW() WHERE gid=%s",
                (json.dumps(meta), gid)
            )
            conn.commit()
    return {"success": True}

# ─── PBOM 差异工作队列 ────────────────────────────────────────────────────────

class DiffQueueGenerateBody(BaseModel):
    pbom_base_gid:   Optional[str] = None
    pbom_target_gid: str


class DiffQueuePatchBody(BaseModel):
    status: str   # pending / done / ignored
    note:   Optional[str] = None


@router.post("/versions/{gid}/pbom-diff-queue", status_code=201)
async def generate_pbom_diff_queue(gid: str, body: DiffQueueGenerateBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_change(request, _u, principal, gateway, {"operation": "pbom_diff_queue.generate", "version_gid": gid, **body.model_dump()})


def _legacy_generate_pbom_diff_queue(gid: str, body: DiffQueueGenerateBody, _u=Depends(_WRITE)):
    """
    生成 PBOM 差异工作队列：对比两个 PBOM 版本，将差异零件写入 bop_pbom_diff_queue。
    已有未处理（pending）条目先清除，重新生成。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_family_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "BOP 版本不存在")
            family_gid = dict(row)['version_family_gid'] or gid

            # 清除旧 pending 条目
            try:
                cur.execute(
                    "DELETE FROM workmanship_bop_bop_pbom_diff_queue "
                    "WHERE bop_version_gid=%s AND status='pending'",
                    (gid,)
                )
            except Exception:
                pass  # 表不存在时跳过

            # 获取新旧 PBOM 零件列表
            target_parts: dict = {}
            cur.execute(
                "SELECT gid, vpps, vpps_desc, bom_row FROM workmanship_bop_pbom "
                "WHERE snapshot_gid=%s",
                (body.pbom_target_gid,)
            )
            for r in cur.fetchall():
                target_parts[r['vpps'] or r['bom_row'] or r['gid']] = dict(r)

            base_keys: set = set()
            if body.pbom_base_gid:
                cur.execute(
                    "SELECT vpps, bom_row FROM workmanship_bop_pbom WHERE snapshot_gid=%s",
                    (body.pbom_base_gid,)
                )
                for r in cur.fetchall():
                    base_keys.add(r['vpps'] or r['bom_row'] or '')

            inserted = 0
            for key, p in target_parts.items():
                diff_type = 'added' if key not in base_keys else 'modified'
                if not body.pbom_base_gid:
                    diff_type = 'added'
                try:
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_pbom_diff_queue "
                        "(gid, family_gid, bop_version_gid, pbom_base_gid, pbom_target_gid,"
                        " pbom_part_gid, diff_type, vpps, vpps_desc) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (str(next_gid()), family_gid, gid,
                         body.pbom_base_gid, body.pbom_target_gid,
                         p['gid'], diff_type, p.get('vpps', ''), p.get('vpps_desc', ''))
                    )
                    inserted += 1
                except Exception:
                    pass

            conn.commit()
    return {"success": True, "inserted": inserted}


@router.get("/versions/{gid}/pbom-diff-queue", status_code=200)
async def get_pbom_diff_queue(gid: str, request: Request, status: Optional[str] = None, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    """查询 PBOM 差异工作队列"""
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.pbom_lifecycle.read", payload={"operation": "diff_queue", "gid": gid, "status": status}, current_user=_u,
        principal=principal, request_id=request.headers.get("X-Request-ID") or f"craft_bop_pbom_diff_queue_legacy_{next_gid()}", trace_id=request.headers.get("X-Trace-ID") or "craft_bop_pbom_diff_queue",
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"invalid_input": 400, "permission_denied": 403}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data


def _legacy_get_pbom_diff_queue(gid: str, status: Optional[str] = None, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                if status:
                    cur.execute(
                        "SELECT * FROM workmanship_bop_bop_pbom_diff_queue "
                        "WHERE bop_version_gid=%s AND status=%s ORDER BY created_at",
                        (gid, status)
                    )
                else:
                    cur.execute(
                        "SELECT * FROM workmanship_bop_bop_pbom_diff_queue "
                        "WHERE bop_version_gid=%s ORDER BY diff_type, vpps",
                        (gid,)
                    )
                return {"data": [dict(r) for r in cur.fetchall()]}
            except Exception:
                return {"data": []}


@router.patch("/pbom-diff-queue/{item_gid}", status_code=200)
async def patch_pbom_diff_item(item_gid: str, body: DiffQueuePatchBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_lifecycle_change(request, _u, principal, gateway, {"operation": "pbom_diff_queue.item.update", "item_gid": item_gid, **body.model_dump()})


def _legacy_patch_pbom_diff_item(item_gid: str, body: DiffQueuePatchBody, _u=Depends(_WRITE)):
    """更新差异队列条目状态"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_bop_bop_pbom_diff_queue "
                "SET status=%s, note=%s, updated_at=NOW() WHERE gid=%s",
                (body.status, body.note, item_gid)
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "条目不存在")
            conn.commit()
    return {"success": True}
