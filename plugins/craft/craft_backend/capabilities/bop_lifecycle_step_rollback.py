"""Governed rollback of one BOP lifecycle checklist step."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec

from ..data.connection import get_craft_conn


STEP_NODE_TYPES = {
    "lines_added": ("line_process",),
    "stations_added": ("asm_station_process", "physical_station"),
    "processes_added": ("asm_operator_process", "asm_operation", "operator_process"),
}
STEP_KEYS = tuple((*STEP_NODE_TYPES, "vpps_imported", "pbom_vpps_checked"))


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _value(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, dict) else dict(row).get(key)


def _state(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value) if value else {}
        except (TypeError, ValueError):
            value = {}
    return dict(value or {})


def _soft_delete_links(cur: Any, where_sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(
        "SELECT COUNT(*) AS count FROM information_schema.columns WHERE table_schema='ai00' AND table_name='bop_entry_links' AND column_name='is_deleted'"
    )
    row = cur.fetchone()
    has_deleted = bool(_value(row, "count")) if row else False
    if has_deleted:
        cur.execute(f"UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE WHERE {where_sql} AND is_deleted=FALSE", params)
    else:
        cur.execute(f"DELETE FROM workmanship_bop_bop_entry_links WHERE {where_sql}", params)
    return int(getattr(cur, "rowcount", 0) or 0)


def apply_bop_lifecycle_step_rollback(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    version_gid = _required(payload, "version_gid")
    step_key = str(payload.get("step_key") or "").strip()
    if step_key not in STEP_KEYS:
        raise ValueError(f"step_key must be one of: {', '.join(STEP_KEYS)}")
    pbom_version_gid = str(payload.get("pbom_version_gid") or "").strip() or None

    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT lifecycle_state FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"版本 {version_gid} 不存在")

        deleted_entries = 0
        deleted_links = 0
        if step_key in STEP_NODE_TYPES:
            node_types = STEP_NODE_TYPES[step_key]
            placeholders = ",".join(["%s"] * len(node_types))
            cur.execute(
                f"WITH RECURSIVE tree AS (SELECT gid FROM workmanship_bop_bop_entries WHERE version_gid=%s AND node_type IN ({placeholders}) AND is_deleted=FALSE UNION ALL SELECT e.gid FROM workmanship_bop_bop_entries e JOIN tree t ON e.parent_gid=t.gid WHERE e.is_deleted=FALSE) SELECT gid FROM tree",
                (version_gid, *node_types),
            )
            gids = [str(_value(item, "gid")) for item in cur.fetchall() if _value(item, "gid")]
            if gids:
                entry_placeholders = ",".join(["%s"] * len(gids))
                cur.execute(f"UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE,deleted_at=NOW() WHERE gid IN ({entry_placeholders})", tuple(gids))
                deleted_entries = int(getattr(cur, "rowcount", 0) or 0)
                deleted_links = _soft_delete_links(cur, f"entry_gid IN ({entry_placeholders})", tuple(gids))
        elif step_key == "vpps_imported":
            if pbom_version_gid:
                deleted_links = _soft_delete_links(cur, "version_gid=%s AND link_type='pbom_part' AND ref_gid IN (SELECT gid FROM workmanship_bop_pbom WHERE snapshot_gid=%s)", (version_gid, pbom_version_gid))
            else:
                deleted_links = _soft_delete_links(cur, "version_gid=%s AND link_type='pbom_part'", (version_gid,))

        state = _state(_value(row, "lifecycle_state"))
        init = _state(state.get("init"))
        checklist = _state(init.get("checklist"))
        checklist[step_key] = False
        init["checklist"] = checklist
        state["init"] = init
        cur.execute("UPDATE workmanship_bop_bop_versions SET lifecycle_state=%s,updated_at=NOW() WHERE gid=%s", (json.dumps(state, ensure_ascii=False), version_gid))
        conn.commit()

    return {"data": {"step_key": step_key, "deleted_entries": deleted_entries, "deleted_links": deleted_links}}


def register_bop_lifecycle_step_rollback_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.lifecycle.step.rollback.apply", owner="craft",
        description="Rollback one BOP lifecycle checklist step and its governed data effects.",
        use_when="A governed Craft consumer explicitly rolls back one supported lifecycle checklist step.",
        do_not_use_when="The request undoes a history batch, restores a checkpoint, or changes lifecycle phase state.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["version_gid", "step_key"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "lifecycle", "rollback", "write"),
    ), apply_bop_lifecycle_step_rollback)


__all__ = ["STEP_KEYS", "apply_bop_lifecycle_step_rollback", "register_bop_lifecycle_step_rollback_capability"]
