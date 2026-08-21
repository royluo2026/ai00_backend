"""Read-only GBOP navigation binding projections."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn

OPERATIONS = ("link_summary", "auto_link_status")


def read_gbop_navigation(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported GBOP navigation read operation")
    pbom_gid = str(payload.get("pbom_version_gid") or "")
    if not pbom_gid:
        raise ValueError("pbom_version_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "link_summary":
                cur.execute("SELECT gbop_op_entry_gid, pbom_entry_gid, confirmed FROM workmanship_bop_gbop_nav_bindings WHERE pbom_version_gid=%s LIMIT 500", (pbom_gid,))
                link_map: dict[str, dict[str, Any]] = {}
                for row in cur.fetchall():
                    op_gid = str(row["gbop_op_entry_gid"])
                    link_map.setdefault(op_gid, {"bop_entry_gid": row["pbom_entry_gid"], "is_valid": True})
                return CapabilityOutput(data={"data": link_map})
            cur.execute("SELECT COUNT(*) AS cnt FROM workmanship_bop_gbop_nav_bindings WHERE pbom_version_gid=%s AND confirmed=FALSE", (pbom_gid,))
            pending = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM workmanship_bop_gbop_nav_bindings WHERE pbom_version_gid=%s AND confirmed=TRUE", (pbom_gid,))
            confirmed = cur.fetchone()["cnt"]
    return CapabilityOutput(data={"data": {"pending_count": pending, "confirmed_count": confirmed}})


def register_gbop_navigation_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.gbop.navigation.read", owner="craft", description="Read bounded GBOP navigation binding projections.", use_when="A governed consumer needs GBOP/PBOM link summary or auto-link status.", do_not_use_when="The request creates, confirms or mutates navigation bindings.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation", "pbom_version_gid"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "pbom_version_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False}, tags=("craft", "gbop", "navigation", "read")), read_gbop_navigation)
