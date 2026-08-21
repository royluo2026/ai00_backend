"""Read bounded PBOM/BOP lifecycle projections."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from ..data.connection import get_craft_conn

OPERATIONS = ("link_stats", "diff_queue")


def read_bop_pbom_lifecycle(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported PBOM lifecycle read operation")
    gid = str(payload.get("gid") or "")
    if not gid:
        raise ValueError("gid is required")
    status = payload.get("status")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "link_stats":
                cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("BOP version not found")
                meta = dict(row).get("meta") or {}
                pbom_gid = (meta.get("pbom_match") or {}).get("pbom_version_gid", "")
                cur.execute("SELECT COUNT(*) AS cnt FROM workmanship_bop_bop_entry_links WHERE version_gid=%s AND link_type='pbom_part'", (gid,))
                linked = (cur.fetchone() or {}).get("cnt", 0) or 0
                total = 0
                if pbom_gid:
                    cur.execute("SELECT COUNT(*) AS cnt FROM workmanship_bop_pbom WHERE snapshot_gid=%s", (pbom_gid,))
                    total = (cur.fetchone() or {}).get("cnt", 0) or 0
                return CapabilityOutput(data={"linked": linked, "total": total, "pbom_version_gid": pbom_gid})
            try:
                if status:
                    cur.execute("SELECT * FROM workmanship_bop_bop_pbom_diff_queue WHERE bop_version_gid=%s AND status=%s ORDER BY created_at LIMIT 500", (gid, status))
                else:
                    cur.execute("SELECT * FROM workmanship_bop_bop_pbom_diff_queue WHERE bop_version_gid=%s ORDER BY diff_type, vpps LIMIT 500", (gid,))
                rows = [dict(item) for item in cur.fetchall()]
            except Exception:
                rows = []
    return CapabilityOutput(data={"data": rows})


def register_bop_pbom_lifecycle_read_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.bop.pbom_lifecycle.read", owner="craft", description="Read bounded PBOM link statistics and diff queue projections for a BOP version.", use_when="A governed consumer needs PBOM matching status or the read-only diff queue.", do_not_use_when="The request changes PBOM matching metadata or diff queue state.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation", "gid"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "gid": {"type": "string"}, "status": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "additionalProperties": True}, tags=("craft", "bop", "pbom", "lifecycle", "read")), read_bop_pbom_lifecycle)
