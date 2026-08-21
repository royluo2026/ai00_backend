"""Bounded read projections for BOP lifecycle history and checkpoints."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from ..data.connection import get_craft_conn

OPERATIONS = ("history", "checkpoints", "line_history", "operation_log")


def read_bop_lifecycle(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported BOP lifecycle read operation")
    gid = str(payload.get("gid") or "")
    if not gid:
        raise ValueError("gid is required")
    line_gid = str(payload.get("line_gid") or "")
    limit = payload.get("limit", 50)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "history":
                cur.execute("SELECT * FROM workmanship_bop_bop_lifecycle_history WHERE version_gid=%s ORDER BY entered_at LIMIT 500", (gid,))
                return CapabilityOutput(data={"data": [dict(row) for row in cur.fetchall()]})
            if not line_gid:
                raise ValueError("line_gid is required for this lifecycle operation")
            if operation == "checkpoints":
                cur.execute("SELECT gid,label,created_by,created_by_name,created_at FROM workmanship_bop_bop_line_checkpoints WHERE version_gid=%s AND line_gid=%s ORDER BY created_at DESC LIMIT 500", (gid, line_gid))
                return CapabilityOutput(data={"data": [dict(row) for row in cur.fetchall()]})
            cur.execute("SELECT gid FROM workmanship_bop_bop_entries WHERE gid=%s AND version_gid=%s AND is_deleted=FALSE", (line_gid, gid))
            if not cur.fetchone():
                return CapabilityOutput(data={"data": [], "latest_active_batch_id": None})
            if operation == "line_history":
                cur.execute("SELECT gid,batch_id,op_type,entity_gid,entity_title,old_state,new_state,op_seq,performed_by,performed_by_name,performed_at,rolled_back,batch_status,invalidate_reason FROM workmanship_bop_bop_line_operation_log WHERE version_gid=%s AND line_gid=%s ORDER BY performed_at DESC,op_seq DESC LIMIT %s", (gid, line_gid, limit))
                items = [dict(row) for row in cur.fetchall()]
                cur.execute("SELECT batch_id FROM workmanship_bop_bop_line_operation_log WHERE version_gid=%s AND line_gid=%s AND batch_status='active' ORDER BY performed_at DESC,op_seq DESC LIMIT 1", (gid, line_gid))
                latest = cur.fetchone()
                return CapabilityOutput(data={"data": items, "latest_active_batch_id": latest.get("batch_id") if latest else None})
            cur.execute("SELECT gid,batch_id,op_type,entity_gid,entity_title,op_seq,performed_by,performed_by_name,performed_at,rolled_back,batch_status,undone_at,undone_by,redone_at,redone_by,invalidate_reason FROM workmanship_bop_bop_line_operation_log WHERE version_gid=%s AND line_gid=%s ORDER BY performed_at DESC,op_seq DESC LIMIT %s", (gid, line_gid, limit))
            return CapabilityOutput(data={"data": [dict(row) for row in cur.fetchall()]})


def register_bop_lifecycle_read_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.bop.lifecycle.read", owner="craft", description="Read bounded BOP lifecycle history, checkpoints and operation logs.", use_when="A governed consumer needs lifecycle audit projections for a BOP version or line.", do_not_use_when="The request changes lifecycle state, checkpoints, or operation history.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation", "gid"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "gid": {"type": "string"}, "line_gid": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "latest_active_batch_id": {"type": ["string", "null"]}}, "additionalProperties": False}, tags=("craft", "bop", "lifecycle", "read")), read_bop_lifecycle)
