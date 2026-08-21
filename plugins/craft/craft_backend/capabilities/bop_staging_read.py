"""Bounded read projection for legacy BOP staging."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn

OPERATIONS = ("list",)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def read_bop_staging(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    if payload.get("operation") != "list":
        raise ValueError("unsupported BOP staging read operation")
    version_gid = str(payload.get("version_gid") or "")
    if not version_gid:
        raise ValueError("version_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid,bop_version_gid,node_type,title,vpps,source_type,source_ref_gid,original_entry_gid,child_count,meta,sort_order,created_at,created_by FROM workmanship_bop_bop_staging WHERE bop_version_gid=%s ORDER BY sort_order,created_at", (version_gid,))
            rows = [{key: _jsonable(value) for key, value in dict(row).items()} for row in cur.fetchall()]
    return CapabilityOutput(data={"data": rows})


def register_bop_staging_read_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.staging.read", owner="craft",
        description="Read BOP staging entries for a version.",
        use_when="A governed Craft consumer needs the legacy staging list projection.",
        do_not_use_when="The request creates, edits, deletes, demotes, or promotes staging entries.",
        risk="read", permissions=("craft.read",),
        input_schema={"type": "object", "required": ["operation", "version_gid"], "properties": {"operation": {"type": "string", "enum": ["list"]}, "version_gid": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False},
        tags=("craft", "bop", "staging", "read"),
    ), read_bop_staging)
