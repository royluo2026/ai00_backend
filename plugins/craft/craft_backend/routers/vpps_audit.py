"""
backend/routers/vpps_audit.py
──────────────────────────────
VPPS 操作审计 API

端点：
  POST /api/vpps-operations/rule4-bulk-ignore
  GET  /api/vpps-operations
  GET  /api/vpps-operations/rule4-ignores
  POST /api/vpps-operations/{gid}/revert
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.domain.vpps_audit.service import VppsAuditService
from backend.infra.vpps_audit_pg import PgVppsOperationRepository
from backend.routers.deps import get_current_user, require_role

router = APIRouter(prefix="/api/vpps-operations", tags=["vpps_audit"])

_READ  = require_role("super_admin", "team_admin", "project_admin",
                      "rule_admin", "knowledge_admin", "member")
_WRITE = require_role("super_admin", "team_admin", "project_admin", "member")


# ── Request Bodies ────────────────────────────────────────────────────────────

class IgnoreRow(BaseModel):
    pbom_row_gid: str
    original_vpps_desc: Optional[str] = None
    notes: Optional[str] = None


class BulkIgnoreRule4Body(BaseModel):
    pbom_version_gid: str
    rows: list[IgnoreRow]
    actor_gid: Optional[str] = None
    actor_name: Optional[str] = None


class RevertBody(BaseModel):
    reverted_by_gid: Optional[str] = None
    reverted_by_name: Optional[str] = None


# ── 辅助：序列化 VppsOperation ────────────────────────────────────────────────

def _op_to_dict(op) -> dict:
    return {
        "gid":              op.gid,
        "pbom_version_gid": op.pbom_version_gid,
        "pbom_row_gid":     op.pbom_row_gid,
        "operation_type":   op.operation_type,
        "rule_no":          op.rule_no,
        "field_name":       op.field_name,
        "original_value":   op.original_value,
        "new_value":        op.new_value,
        "actor_gid":        op.actor_gid,
        "actor_name":       op.actor_name,
        "created_at":       op.created_at.isoformat() if op.created_at else None,
        "notes":            op.notes,
        "is_active":        op.is_active,
        "reverted_at":      op.reverted_at.isoformat() if op.reverted_at else None,
        "reverted_by_gid":  op.reverted_by_gid,
        "reverted_by_name": op.reverted_by_name,
    }


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.post("/rule4-bulk-ignore", dependencies=[Depends(_WRITE)])
def rule4_bulk_ignore(body: BulkIgnoreRule4Body, user: dict = Depends(get_current_user)):
    """一键忽略规则4全部 NOK 行。幂等：已忽略的行会被跳过。"""
    actor_gid  = body.actor_gid  or user["gid"]
    actor_name = body.actor_name or user.get("name", "")
    rows = [r.model_dump() for r in body.rows]

    with get_conn() as conn:
        repo    = PgVppsOperationRepository(conn)
        service = VppsAuditService(repo)
        ops     = service.bulk_ignore_rule4(
            pbom_version_gid=body.pbom_version_gid,
            rows=rows,
            actor_gid=actor_gid,
            actor_name=actor_name,
        )
        conn.commit()

    return {
        "success":    True,
        "created":    len(ops),
        "operations": [_op_to_dict(o) for o in ops],
    }


@router.get("", dependencies=[Depends(_READ)])
def list_operations(
    pbom_version_gid: str,
    operation_type: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """返回指定 PBOM 版本的 is_active 操作记录列表。"""
    with get_conn() as conn:
        repo    = PgVppsOperationRepository(conn)
        service = VppsAuditService(repo)
        ops     = service.get_active_operations(pbom_version_gid, operation_type)

    return {"success": True, "data": [_op_to_dict(o) for o in ops]}


@router.get("/rule4-ignores", dependencies=[Depends(_READ)])
def get_rule4_ignores(pbom_version_gid: str, user: dict = Depends(get_current_user)):
    """返回该 PBOM 版本中已忽略的 rule4 pbom_row_gid 集合及操作详情。"""
    with get_conn() as conn:
        repo    = PgVppsOperationRepository(conn)
        service = VppsAuditService(repo)
        ops     = service.get_active_operations(pbom_version_gid, "rule4_bulk_ignore")
        gids    = {op.pbom_row_gid for op in ops}

    return {
        "success":          True,
        "ignored_row_gids": sorted(gids),
        "operations":       [_op_to_dict(o) for o in ops],
    }


@router.post("/{gid}/revert", dependencies=[Depends(_WRITE)])
def revert_operation(gid: str, body: RevertBody, user: dict = Depends(get_current_user)):
    """撤销指定操作（is_active → FALSE）。"""
    reverted_by_gid  = body.reverted_by_gid  or user["gid"]
    reverted_by_name = body.reverted_by_name or user.get("name", "")

    with get_conn() as conn:
        repo    = PgVppsOperationRepository(conn)
        service = VppsAuditService(repo)
        op      = service.revert_operation(gid, reverted_by_gid, reverted_by_name)
        conn.commit()

    if not op:
        raise HTTPException(status_code=404, detail="操作不存在或已撤销")

    return {"success": True, "operation": _op_to_dict(op)}
