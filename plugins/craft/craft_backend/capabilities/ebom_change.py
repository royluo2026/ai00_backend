"""Governed PBOM compatibility mutations exposed by the legacy EBOM routes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn


OPERATIONS = (
    "snapshot.delete",
    "snapshot.patch",
    "snapshot.status.patch",
    "snapshot.vpps_stats.patch",
    "part.add",
    "part.add_batch",
    "part.update",
    "part.delete",
)
ALLOWED_STATUSES = {"raw", "ready", "draft"}
SNAPSHOT_FIELDS = {"name", "version_tag", "visibility", "shared_team_gid", "shared_project_gid"}
PART_FIELDS = {
    "part_no", "name", "quantity", "unit", "material", "parent_gid", "vpps", "vpps_desc", "parent_vpps",
    "parent_vpps_name", "bom_row", "bom_row_label", "component_id", "component_type",
    "component_version_status", "purchase_status", "variable_formula", "torque", "torque_importance",
    "ownership_user", "level", "home", "configuration", "parent_bom_row", "remark", "temp_vpps",
    "catia_occurrence_name", "catia_file_name", "catia_uuid", "default_matrix", "abs_matrix", "rel_matrix",
    "local_bbox", "ecn", "fna", "geo_main_part", "ref_main_vpps_desc", "ref_main_vpps",
    "main_part_consistency", "geo_evidence", "lr_side",
}
PART_COLUMN = {"name": "title"}
MAX_BATCH = 500


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _non_negative(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _part_insert(cur, snapshot_gid: str, part: dict[str, Any]) -> str:
    unknown = set(part) - PART_FIELDS
    if unknown:
        raise ValueError(f"unsupported part fields: {', '.join(sorted(unknown))}")
    part_no = str(part.get("part_no") or "").strip()
    if not part_no:
        raise ValueError("part_no is required")
    part_gid = str(part.get("gid") or next_gid())
    values: dict[str, Any] = {
        "gid": part_gid, "snapshot_gid": snapshot_gid, "part_no": part_no,
        "title": str(part.get("name") or ""), "quantity": part.get("quantity", 1),
        "unit": part.get("unit", "pcs"), "material": part.get("material"),
        "vpps_source": "auto", "is_deleted": 0, "meta": "{}",
    }
    for key in PART_FIELDS - {"name", "part_no", "quantity", "unit", "material"}:
        values[PART_COLUMN.get(key, key)] = part.get(key)
    columns = list(values)
    placeholders = ",".join(["%s"] * len(columns))
    cur.execute(
        f"INSERT INTO workmanship_bop_pbom ({','.join(columns)}) VALUES ({placeholders})",
        [values[column] for column in columns],
    )
    return part_gid


def apply_ebom_change(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")

    if operation == "snapshot.delete":
        snapshot_gid = _required(payload, "snapshot_gid")
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_bop_pbom_versions WHERE gid=%s", (snapshot_gid,))
            if cur.rowcount == 0:
                raise CapabilityBusinessError("resource_not_found", "PBOM version does not exist")
            conn.commit()
        return {"data": {"success": True, "snapshot_gid": snapshot_gid}}

    if operation == "snapshot.patch":
        snapshot_gid = _required(payload, "snapshot_gid")
        changes = payload.get("changes")
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        unknown = set(changes) - SNAPSHOT_FIELDS
        if unknown:
            raise ValueError(f"unsupported snapshot fields: {', '.join(sorted(unknown))}")
        if not changes:
            raise ValueError("changes must not be empty")
        assignments = ", ".join(f"{field}=%s" for field in changes)
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_bop_pbom_versions SET {assignments} WHERE gid=%s", [*changes.values(), snapshot_gid])
            if cur.rowcount == 0:
                raise CapabilityBusinessError("resource_not_found", "PBOM version does not exist")
            conn.commit()
        return {"data": {"success": True, "snapshot_gid": snapshot_gid}}

    if operation == "snapshot.status.patch":
        snapshot_gid = _required(payload, "snapshot_gid")
        status = str(payload.get("status") or "").strip()
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}")
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE workmanship_bop_pbom_versions SET status=%s WHERE gid=%s", (status, snapshot_gid))
            if cur.rowcount == 0:
                raise CapabilityBusinessError("resource_not_found", "PBOM version does not exist")
            conn.commit()
        return {"data": {"success": True, "snapshot_gid": snapshot_gid, "status": status}}

    if operation == "snapshot.vpps_stats.patch":
        snapshot_gid = _required(payload, "snapshot_gid")
        stats = {name: _non_negative(payload, name) for name in ("nok", "ignored", "total")}
        stats["checked_at"] = datetime.now(timezone.utc).isoformat()
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT meta FROM workmanship_bop_pbom_versions WHERE gid=%s", (snapshot_gid,))
            row = cur.fetchone()
            if not row:
                raise CapabilityBusinessError("resource_not_found", "PBOM version does not exist")
            meta = row.get("meta") if isinstance(row, dict) else dict(row).get("meta")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta) if meta else {}
                except (TypeError, ValueError):
                    meta = {}
            meta = dict(meta or {})
            meta["vpps_check"] = stats
            cur.execute("UPDATE workmanship_bop_pbom_versions SET meta=%s WHERE gid=%s", (json.dumps(meta), snapshot_gid))
            conn.commit()
        return {"data": {"success": True, "vpps_check": stats}}

    if operation == "part.add_batch":
        snapshot_gid = _required(payload, "snapshot_gid")
        parts = payload.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("parts must be a non-empty array")
        if len(parts) > MAX_BATCH:
            raise ValueError(f"parts must contain at most {MAX_BATCH} items")
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_bop_pbom_versions WHERE gid=%s", (snapshot_gid,))
            if not cur.fetchone():
                raise CapabilityBusinessError("resource_not_found", "PBOM version does not exist")
            inserted = [_part_insert(cur, snapshot_gid, item) for item in parts if isinstance(item, dict)]
            if len(inserted) != len(parts):
                raise ValueError("each part must be an object")
            conn.commit()
        return {"data": {"success": True, "data": {"inserted": len(inserted)}, "inserted": len(inserted), "part_gids": inserted}}

    if operation == "part.add":
        snapshot_gid = _required(payload, "snapshot_gid")
        part = payload.get("part")
        if not isinstance(part, dict):
            raise ValueError("part must be an object")
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM workmanship_bop_pbom_versions WHERE gid=%s", (snapshot_gid,))
            if not cur.fetchone():
                raise CapabilityBusinessError("resource_not_found", "PBOM version does not exist")
            part_gid = _part_insert(cur, snapshot_gid, part)
            conn.commit()
        return {"data": {"success": True, "data": {"gid": part_gid}, "part_gid": part_gid}}

    part_gid = _required(payload, "part_gid")
    if operation == "part.delete":
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_bop_pbom WHERE gid=%s", (part_gid,))
            if cur.rowcount == 0:
                raise CapabilityBusinessError("resource_not_found", "PBOM part does not exist")
            conn.commit()
        return {"data": {"success": True, "part_gid": part_gid}}

    changes = payload.get("changes")
    if not isinstance(changes, dict):
        raise ValueError("changes must be an object")
    unknown = set(changes) - PART_FIELDS
    if unknown:
        raise ValueError(f"unsupported part fields: {', '.join(sorted(unknown))}")
    if not changes:
        raise ValueError("changes must not be empty")
    changes = {PART_COLUMN.get(key, key): value for key, value in changes.items()}
    assignments = ", ".join(f"{field}=%s" for field in changes)
    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE workmanship_bop_pbom SET {assignments} WHERE gid=%s", [*changes.values(), part_gid])
        if cur.rowcount == 0:
            raise CapabilityBusinessError("resource_not_found", "PBOM part does not exist")
        conn.commit()
    return {"data": {"success": True, "part_gid": part_gid}}


def register_ebom_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.ebom.change.apply", owner="craft",
        description="Apply bounded PBOM compatibility snapshot and part mutations through the governed Craft Provider.",
        use_when="A legacy EBOM/PBOM REST consumer creates, updates, deletes or transitions a PBOM snapshot or part.",
        do_not_use_when="The operation is a read, PBOM version lifecycle transition, or BOP/GBOP mutation.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "ebom", "pbom", "write"),
    ), apply_ebom_change)


__all__ = ["OPERATIONS", "apply_ebom_change", "register_ebom_change_capability"]
