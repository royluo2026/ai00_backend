"""Transactional BOP lifecycle metadata and PBOM diff-queue mutations."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn


OPERATIONS = (
    "pbom_match.update",
    "vehicle_ops_stats.update",
    "pbom_diff_queue.generate",
    "pbom_diff_queue.item.update",
)
MAX_PARTS = 5000


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _counter(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def apply_bop_lifecycle_change(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")

    if operation in {"pbom_match.update", "vehicle_ops_stats.update"}:
        version_gid = _required(payload, "version_gid")
        if operation == "pbom_match.update":
            value = {"pbom_version_gid": _required(payload, "pbom_version_gid"), "unlinked_ignored": _counter(payload, "unlinked_ignored")}
            key = "pbom_match"
        else:
            value = {"confirmed": _counter(payload, "confirmed"), "skipped": _counter(payload, "skipped"), "total": _counter(payload, "total")}
            key = "vehicle_ops_prep"
        with get_craft_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
                row = cur.fetchone()
                if not row:
                    raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
                meta = row.get("meta") if isinstance(row, dict) else dict(row)["meta"]
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta) if meta else {}
                    except (TypeError, ValueError):
                        meta = {}
                meta = dict(meta or {})
                meta[key] = value
                cur.execute("UPDATE workmanship_bop_bop_versions SET meta=%s, updated_at=NOW() WHERE gid=%s", (json.dumps(meta, ensure_ascii=False), version_gid))
            conn.commit()
        return {"success": True, key: value}

    if operation == "pbom_diff_queue.item.update":
        item_gid = _required(payload, "item_gid")
        status = str(payload.get("status") or "").strip()
        if status not in {"pending", "done", "ignored"}:
            raise ValueError("status must be pending, done, or ignored")
        with get_craft_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_bop_bop_pbom_diff_queue SET status=%s, note=%s, updated_at=NOW() WHERE gid=%s", (status, payload.get("note"), item_gid))
                if cur.rowcount == 0:
                    raise CapabilityBusinessError("resource_not_found", f"PBOM diff queue item {item_gid} does not exist")
            conn.commit()
        return {"success": True, "item_gid": item_gid, "status": status}

    version_gid = _required(payload, "version_gid")
    target_gid = _required(payload, "pbom_target_gid")
    base_gid = str(payload.get("pbom_base_gid") or "").strip() or None
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_family_gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
            row = cur.fetchone()
            if not row:
                raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
            family_gid = (dict(row).get("version_family_gid") or version_gid)
            cur.execute("SELECT gid, vpps, vpps_desc, bom_row FROM workmanship_bop_pbom WHERE snapshot_gid=%s LIMIT %s", (target_gid, MAX_PARTS))
            target_parts = [dict(item) for item in cur.fetchall()]
            if len(target_parts) >= MAX_PARTS:
                raise CapabilityBusinessError("response_limit_exceeded", "PBOM diff queue exceeds the bounded part limit", details={"limit": MAX_PARTS})
            base_keys: set[str] = set()
            if base_gid:
                cur.execute("SELECT vpps, bom_row FROM workmanship_bop_pbom WHERE snapshot_gid=%s LIMIT %s", (base_gid, MAX_PARTS))
                base_keys = {str(item.get("vpps") or item.get("bom_row") or "") for item in cur.fetchall()}
            cur.execute("DELETE FROM workmanship_bop_bop_pbom_diff_queue WHERE bop_version_gid=%s AND status='pending'", (version_gid,))
            inserted = 0
            for part in target_parts:
                key = part.get("vpps") or part.get("bom_row") or part.get("gid")
                diff_type = "added" if not base_gid or key not in base_keys else "modified"
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_pbom_diff_queue (gid,family_gid,bop_version_gid,pbom_base_gid,pbom_target_gid,pbom_part_gid,diff_type,vpps,vpps_desc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (str(next_gid()), family_gid, version_gid, base_gid, target_gid, part["gid"], diff_type, part.get("vpps", ""), part.get("vpps_desc", "")),
                )
                inserted += 1
        conn.commit()
    return {"success": True, "inserted": inserted, "version_gid": version_gid}


def register_bop_lifecycle_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.lifecycle.change.apply", owner="craft",
        description="Apply bounded transactional BOP lifecycle metadata and PBOM diff-queue changes.",
        use_when="A governed Craft consumer updates PBOM matching statistics or regenerates/updates a diff queue.",
        do_not_use_when="The request changes lifecycle phases, checkpoints, line history, or BOP entities.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": True},
        tags=("craft", "bop", "lifecycle", "write"),
    ), apply_bop_lifecycle_change)


__all__ = ["OPERATIONS", "apply_bop_lifecycle_change", "register_bop_lifecycle_change_capability"]
