"""
backend/routers/_bop/staging.py
────────────────────────────────
暂存区 CRUD + demote/promote。
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...data.connection import get_conn
from backend.platform_sdk.ids import next_gid
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility

from ._constants import _WRITE, _READ, _AI00_LEVEL
from ._helpers import _not_found, _check_version_frozen, _check_frozen_by_version, _parent_level, _sync_child_vpps, _log_entry_op, _check_line_editable

router = APIRouter(prefix="/api/bop", tags=["bop"])


async def _invoke_staging_read(request, current_user, principal, gateway, version_gid: str, *, capability_id="craft.bop.staging.read"):
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload={"operation": "list", "version_gid": version_gid},
        current_user=current_user, principal=principal,
        request_id=request.headers.get("X-Request-ID") or f"craft_bop_staging_read_{next_gid()}",
        trace_id=request.headers.get("X-Trace-ID") or "craft_bop_staging_read",
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"invalid_input": 400, "permission_denied": 403, "resource_not_found": 404}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data


async def _invoke_staging_change(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_staging_change_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.staging.change.apply", payload=payload,
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


async def _invoke_staging_lifecycle_change(request, current_user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"craft_bop_staging_lifecycle_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="craft.bop.staging.lifecycle.change.apply", payload=payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    ))
    if not result.ok:
        error = result.error
        code = error.code if error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "invalid_input": 400, "invalid_state": 409, "permission_denied": 403}.get(code, 422), detail=error.model_dump(mode="json") if error else None)
    return result.data["data"]


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class CreateStagingBody(BaseModel):
    node_type: str = 'process'
    title: str = ''
    vpps: Optional[str] = None
    source_type: Optional[str] = None
    source_ref_gid: Optional[str] = None
    meta: Optional[dict] = None
    sort_order: float = 0


class PromoteBody(BaseModel):
    parent_gid: Optional[str] = None
    sort_order: float = 0


# ══════════════════════════════════════════════════════════════
# 暂存箱 CRUD
# ══════════════════════════════════════════════════════════════

@router.get("/versions/{version_gid}/staging")
async def list_staging(version_gid: str, request: Request, _u=Depends(_READ), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_staging_read(request, _u, principal, gateway, version_gid, capability_id="craft.bop.staging.read")


def _legacy_list_staging(version_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, bop_version_gid, node_type, title, vpps, "
                "source_type, source_ref_gid, original_entry_gid, "
                "child_count, meta, sort_order, created_at, created_by "
                "FROM workmanship_bop_bop_staging WHERE bop_version_gid=%s ORDER BY sort_order, created_at",
                (version_gid,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": rows}


@router.post("/versions/{version_gid}/staging", status_code=201)
async def create_staging(version_gid: str, body: CreateStagingBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_staging_change(request, _u, principal, gateway, {"operation": "create", "version_gid": version_gid, **body.model_dump()})


def _legacy_create_staging(version_gid: str, body: CreateStagingBody, _u=Depends(_WRITE)):
    _check_frozen_by_version(version_gid)
    gid = str(next_gid())
    user_gid = _u.get('gid') if isinstance(_u, dict) else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_bop_bop_staging "
                "(gid, bop_version_gid, node_type, title, vpps, "
                " source_type, source_ref_gid, meta, sort_order, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, version_gid, body.node_type, body.title, body.vpps,
                 body.source_type, body.source_ref_gid,
                 json.dumps(body.meta or {}), body.sort_order, user_gid),
            )
            conn.commit()
    return {"data": {"gid": gid}}


@router.patch("/staging/{gid}")
async def patch_staging(gid: str, body: dict, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_staging_change(request, _u, principal, gateway, {"operation": "update", "staging_gid": gid, "updates": body})


def _legacy_patch_staging(gid: str, body: dict, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bop_version_gid FROM workmanship_bop_bop_staging WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                _not_found(gid)
            _check_version_frozen(cur, row['bop_version_gid'])
            sets, vals = [], []
            for col in ('title', 'node_type', 'vpps'):
                if col in body:
                    sets.append(f"{col}=%s")
                    vals.append(body[col])
            if not sets:
                return {"data": dict(row)}
            vals.append(gid)
            cur.execute(f"UPDATE workmanship_bop_bop_staging SET {','.join(sets)} WHERE gid=%s", vals)
            cur.execute("SELECT * FROM workmanship_bop_bop_staging WHERE gid=%s", (gid,))
            updated = cur.fetchone()
            conn.commit()
    return {"data": dict(updated) if updated else None}


@router.delete("/staging/{gid}", status_code=204)
async def delete_staging(gid: str, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _invoke_staging_change(request, _u, principal, gateway, {"operation": "delete", "staging_gid": gid})
    return None


def _legacy_delete_staging(gid: str, _u=Depends(_WRITE)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bop_version_gid FROM workmanship_bop_bop_staging WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                _not_found(gid)
            _check_version_frozen(cur, row['bop_version_gid'])
            cur.execute("DELETE FROM workmanship_bop_bop_staging WHERE gid=%s", (gid,))
            conn.commit()


# ── Demote：主视图 bop_entry → 暂存箱 ────────────────────────────────────────

@router.post("/entries/{gid}/demote", status_code=201)
async def demote_entry(gid: str, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_staging_lifecycle_change(request, _u, principal, gateway, {"operation": "demote", "entry_gid": gid})


def _legacy_demote_entry(gid: str, _u=Depends(_WRITE)):
    """将 bop_entry（含后代）soft-delete 并创建暂存项"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, version_gid, parent_gid, node_type, title, vpps "
                "FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted = FALSE",
                (gid,),
            )
            entry = cur.fetchone()
            if not entry:
                _not_found(gid)
            _check_version_frozen(cur, entry['version_gid'])
            _check_line_editable(cur, entry['version_gid'], gid, _u)

            descendant_gids = []
            queue = [gid]
            while queue:
                parent = queue.pop()
                cur.execute(
                    "SELECT gid FROM workmanship_bop_bop_entries "
                    "WHERE parent_gid=%s AND is_deleted = FALSE",
                    (parent,),
                )
                children = [r['gid'] for r in cur.fetchall()]
                descendant_gids.extend(children)
                queue.extend(children)

            all_gids = [gid] + descendant_gids
            _ph = ",".join(["%s"] * len(all_gids))
            cur.execute(
                f"UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW() WHERE gid IN ({_ph})",
                all_gids,
            )

            if entry['parent_gid']:
                _sync_child_vpps(cur, entry['parent_gid'], entry['version_gid'])

            staging_gid = str(next_gid())
            user_gid = _u.get('gid') if isinstance(_u, dict) else None
            cur.execute(
                "INSERT INTO workmanship_bop_bop_staging "
                "(gid, bop_version_gid, node_type, title, vpps, "
                " source_type, original_entry_gid, child_count, created_by) "
                "VALUES (%s,%s,%s,%s,%s,'bop_entry',%s,%s,%s)",
                (staging_gid, entry['version_gid'], entry['node_type'],
                 entry['title'], entry['vpps'], gid, len(descendant_gids), user_gid),
            )
            _log_entry_op(cur,
                version_gid=entry['version_gid'],
                entry_gid=gid, entry_title=entry.get('title') or '',
                op_type='demote_entry',
                old_state={
                    'parent_gid': entry.get('parent_gid'),
                    'node_type': entry.get('node_type'),
                    'title': entry.get('title'),
                    'vpps': entry.get('vpps'),
                },
                new_state={
                    'staging_gid': staging_gid,
                    'child_count': len(descendant_gids),
                },
                user_gid=_u.get('gid', ''), user_name=_u.get('name', ''))
            conn.commit()

    return {"data": {"staging_gid": staging_gid, "child_count": len(descendant_gids)}}


# ── Promote：暂存箱 → 主视图 ──────────────────────────────────────────────────

@router.post("/staging/{gid}/promote", status_code=201)
async def promote_staging(gid: str, body: PromoteBody, request: Request, _u=Depends(_WRITE), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_staging_lifecycle_change(request, _u, principal, gateway, {"operation": "promote", "staging_gid": gid, **body.model_dump()})


def _legacy_promote_staging(gid: str, body: PromoteBody, _u=Depends(_WRITE)):
    """提升暂存项到主视图"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_bop_bop_staging WHERE gid=%s", (gid,))
            staging = cur.fetchone()
            if not staging:
                _not_found(gid)
            version_gid = staging['bop_version_gid']
            _check_version_frozen(cur, version_gid)
            if body.parent_gid:
                _check_line_editable(cur, version_gid, body.parent_gid, _u)

            result_gid = None

            if staging['original_entry_gid']:
                orig_gid = staging['original_entry_gid']

                restore_gids = [orig_gid]
                queue = [orig_gid]
                while queue:
                    parent = queue.pop()
                    cur.execute(
                        "SELECT gid FROM workmanship_bop_bop_entries "
                        "WHERE parent_gid=%s AND is_deleted = TRUE",
                        (parent,),
                    )
                    children = [r['gid'] for r in cur.fetchall()]
                    restore_gids.extend(children)
                    queue.extend(children)

                _ph = ",".join(["%s"] * len(restore_gids))
                cur.execute(
                    f"UPDATE workmanship_bop_bop_entries SET is_deleted=FALSE, deleted_at=NULL WHERE gid IN ({_ph})",
                    restore_gids,
                )
                if body.parent_gid is not None:
                    cur.execute(
                        "UPDATE workmanship_bop_bop_entries SET parent_gid=%s, sort_order=%s WHERE gid=%s",
                        (body.parent_gid, body.sort_order, orig_gid),
                    )
                result_gid = orig_gid
            else:
                if staging['source_type'] and staging['source_ref_gid']:
                    target_gid = body.parent_gid
                    if not target_gid:
                        raise HTTPException(400, "需要指定目标节点 parent_gid")
                    meta = staging['meta'] or {}
                    lt = meta.get('link_type', staging['source_type'])
                    is_primary = meta.get('is_primary', False)
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entry_links "
                        "(gid, entry_gid, version_gid, link_type, entity_gid, is_primary) "
                        "VALUES (%s,%s,%s,%s,%s,%s) "
                        "",
                        (str(next_gid()), target_gid, version_gid, lt, staging['source_ref_gid'], is_primary),
                    )
                    result_gid = target_gid
                else:
                    entry_gid = str(next_gid())
                    level = _parent_level(cur, body.parent_gid)
                    ai00_lv = _AI00_LEVEL.get(staging['node_type'])
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entries "
                        "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level, "
                        " title, vpps, meta) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}')",
                        (entry_gid, version_gid, body.parent_gid,
                         staging['node_type'], body.sort_order, level, ai00_lv,
                         staging['title'], staging['vpps']),
                    )
                    result_gid = entry_gid

            _log_entry_op(cur,
                version_gid=version_gid,
                entry_gid=result_gid or (staging.get('original_entry_gid') or ''),
                entry_title=(staging.get('title') or ''),
                op_type='promote_staging',
                old_state={
                    'staging_gid': gid,
                    'node_type': staging.get('node_type'),
                    'title': staging.get('title'),
                    'vpps': staging.get('vpps'),
                },
                new_state={
                    'entry_gid': result_gid,
                    'parent_gid': body.parent_gid,
                    'sort_order': body.sort_order,
                },
                user_gid=_u.get('gid', ''), user_name=_u.get('name', ''))

            cur.execute("DELETE FROM workmanship_bop_bop_staging WHERE gid=%s", (gid,))
            conn.commit()

    return {"data": {"entry_gid": result_gid}}
