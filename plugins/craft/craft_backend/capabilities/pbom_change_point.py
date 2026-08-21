"""Governed PBOM change-point comparison for a BOP version."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_conn

OPERATION = "get"


def get_pbom_change_point(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    if payload.get("operation") != OPERATION:
        raise ValueError("unsupported PBOM change-point operation")
    gid = str(payload.get("version_gid") or "")
    if not gid:
        raise ValueError("version_gid is required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pbom_version_gid, parent_version_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            version = cur.fetchone()
            if not version:
                raise ValueError("BOP version not found")
            current_gid = version.get("pbom_version_gid")
            parent_gid = version.get("parent_version_gid")
            if not current_gid:
                return CapabilityOutput(data={"data": [], "reason": "当前版本未绑定 PBOM"})
            if not parent_gid:
                return CapabilityOutput(data={"data": [], "reason": "当前版本无父版本，无从对比"})
            cur.execute("SELECT pbom_version_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (parent_gid,))
            parent = cur.fetchone()
            reference_gid = parent.get("pbom_version_gid") if parent else None
            if not reference_gid:
                return CapabilityOutput(data={"data": [], "reason": "父版本未绑定 PBOM，无从对比"})
            query = "SELECT gid, bom_row, vpps, title, part_no, quantity, unit, node_type, updated_at FROM workmanship_bop_pbom WHERE snapshot_gid=%s AND is_deleted=FALSE"
            cur.execute(query, (current_gid,))
            current = {(row["bom_row"], row["vpps"]): dict(row) for row in cur.fetchall() if row["bom_row"] or row["vpps"]}
            cur.execute(query, (reference_gid,))
            reference = {(row["bom_row"], row["vpps"]): dict(row) for row in cur.fetchall() if row["bom_row"] or row["vpps"]}
    changes = []
    fields = ("title", "part_no", "quantity", "unit", "node_type")
    for key, row in current.items():
        if key not in reference:
            changes.append({"change_type": "added", "bom_row": row.get("bom_row"), "vpps": row.get("vpps"), "current": row, "reference": None})
        else:
            old = reference[key]
            diff = {field: (row.get(field), old.get(field)) for field in fields if row.get(field) != old.get(field)}
            if diff:
                changes.append({"change_type": "modified", "bom_row": row.get("bom_row"), "vpps": row.get("vpps"), "current": row, "reference": old, "diff": diff})
    for key, row in reference.items():
        if key not in current:
            changes.append({"change_type": "deleted", "bom_row": row.get("bom_row"), "vpps": row.get("vpps"), "current": None, "reference": row})
    return CapabilityOutput(data={"data": changes, "current_pbom_version_gid": current_gid, "reference_pbom_version_gid": reference_gid, "summary": {"added": sum(item["change_type"] == "added" for item in changes), "modified": sum(item["change_type"] == "modified" for item in changes), "deleted": sum(item["change_type"] == "deleted" for item in changes)}})


def register_pbom_change_point_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.bop.pbom.change_point.get", owner="craft", description="Compare current and parent PBOM snapshots for a BOP version.", use_when="A governed consumer needs PBOM change points for a BOP version.", do_not_use_when="The request mutates a PBOM or compares unrelated versions.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation", "version_gid"], "properties": {"operation": {"type": "string", "enum": [OPERATION]}, "version_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "reason": {"type": "string"}, "current_pbom_version_gid": {"type": "string"}, "reference_pbom_version_gid": {"type": "string"}, "summary": {"type": "object", "additionalProperties": True}}, "additionalProperties": False}, tags=("craft", "bop", "pbom", "read")), get_pbom_change_point)
