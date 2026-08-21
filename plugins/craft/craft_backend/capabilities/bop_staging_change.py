"""Governed BOP staging-area CRUD mutations."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn


OPERATIONS = ("create", "update", "delete")
UPDATE_FIELDS = {"title", "node_type", "vpps"}


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _ensure_active(cur, version_gid: str) -> None:
    cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
    row = cur.fetchone()
    if not row:
        raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
    status = row.get("status") if isinstance(row, dict) else dict(row).get("status")
    if status != "active":
        raise CapabilityBusinessError("invalid_state", f"BOP version is {status}; staging changes require active status")


def apply_bop_staging_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")

    if operation == "create":
        version_gid = _required(payload, "version_gid")
        node_type = str(payload.get("node_type") or "process").strip()
        if not node_type:
            raise ValueError("node_type is required")
        with get_craft_conn() as conn, conn.cursor() as cur:
            _ensure_active(cur, version_gid)
            gid = str(next_gid())
            cur.execute(
                "INSERT INTO workmanship_bop_bop_staging "
                "(gid,bop_version_gid,node_type,title,vpps,source_type,source_ref_gid,meta,sort_order,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, version_gid, node_type, payload.get("title") or "", payload.get("vpps"),
                 payload.get("source_type"), payload.get("source_ref_gid"), json.dumps(payload.get("meta") or {}),
                 payload.get("sort_order", 0), context.user_gid),
            )
            conn.commit()
        return {"data": {"gid": gid}}

    updates = None
    if operation == "update":
        updates = payload.get("updates")
        if not isinstance(updates, dict):
            raise ValueError("updates must be an object")
        unknown = set(updates) - UPDATE_FIELDS
        if unknown:
            raise ValueError(f"unsupported staging fields: {', '.join(sorted(unknown))}")
        if not updates:
            raise ValueError("updates must not be empty")

    staging_gid = _required(payload, "staging_gid")
    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT bop_version_gid FROM workmanship_bop_bop_staging WHERE gid=%s", (staging_gid,))
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"staging entry {staging_gid} does not exist")
        version_gid = row.get("bop_version_gid") if isinstance(row, dict) else dict(row).get("bop_version_gid")
        _ensure_active(cur, version_gid)
        if operation == "delete":
            cur.execute("DELETE FROM workmanship_bop_bop_staging WHERE gid=%s", (staging_gid,))
            conn.commit()
            return {"data": {"success": True, "staging_gid": staging_gid}}
        assert updates is not None
        assignments = ",".join(f"{field}=%s" for field in updates)
        cur.execute(f"UPDATE workmanship_bop_bop_staging SET {assignments} WHERE gid=%s", [*updates.values(), staging_gid])
        conn.commit()
    return {"data": {"success": True, "staging_gid": staging_gid, "updates": updates}}


def register_bop_staging_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.staging.change.apply", owner="craft",
        description="Create, update, or delete active-version BOP staging entries.",
        use_when="A governed Craft consumer mutates the staging area without promoting entries into the BOP tree.",
        do_not_use_when="The request demotes/promotes an entry or mutates BOP entry history.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "staging", "write"),
    ), apply_bop_staging_change)


__all__ = ["OPERATIONS", "apply_bop_staging_change", "register_bop_staging_change_capability"]
