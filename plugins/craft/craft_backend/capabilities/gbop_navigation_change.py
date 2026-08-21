"""Governed GBOP/PBOM navigation binding mutations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn

OPERATIONS = ("confirm", "auto_link")


def change_gbop_navigation(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported GBOP navigation change operation")
    pbom_gid = str(payload.get("pbom_version_gid") or "")
    if not pbom_gid:
        raise ValueError("pbom_version_gid is required")
    if operation == "confirm":
        with get_craft_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_bop_gbop_nav_bindings SET confirmed=TRUE "
                    "WHERE pbom_version_gid=%s AND confirmed=FALSE", (pbom_gid,),
                )
                updated = cur.rowcount
            conn.commit()
        return CapabilityOutput(data={"data": {"ok": True, "confirmed": updated}})

    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM workmanship_bop_gbop_nav_bindings "
                "WHERE pbom_version_gid=%s AND confirmed=FALSE", (pbom_gid,),
            )
            pending = cur.fetchone()["cnt"]
            if pending > 0:
                raise CapabilityBusinessError("conflict", f"存在 {pending} 条未提交的 Auto-Link 绑定，请先确认绑定。")
            cur.execute(
                "SELECT gid, vpps FROM workmanship_bop_pbom "
                "WHERE snapshot_gid=%s AND COALESCE(is_deleted,FALSE)=FALSE "
                "AND vpps IS NOT NULL AND vpps != '' LIMIT 500", (pbom_gid,),
            )
            parts = [dict(row) for row in cur.fetchall()]
            if not parts:
                return CapabilityOutput(data={"data": {"bound": 0, "parts_matched": 0}})
            part_vpps = list({part["vpps"] for part in parts})
            placeholders = ",".join(["%s"] * len(part_vpps))
            cur.execute(
                f"SELECT e.gid AS entry_gid, e.vpps_part, e.parent_gid "
                f"FROM workmanship_tpl_gbop_entries e "
                f"JOIN workmanship_tpl_gbop_versions v ON v.gid=e.version_gid "
                f"WHERE e.node_type='operation' AND e.part_feed=TRUE "
                f"AND e.vpps_part IN ({placeholders}) AND v.archived_at IS NULL LIMIT 500",
                part_vpps,
            )
            operations = [dict(row) for row in cur.fetchall()]
            if not operations:
                return CapabilityOutput(data={"data": {"bound": 0, "parts_matched": 0}})
            parent_gids = list({row["parent_gid"] for row in operations if row.get("parent_gid")})
            parent_map: dict[Any, dict[str, Any]] = {}
            if parent_gids:
                placeholders = ",".join(["%s"] * len(parent_gids))
                cur.execute(
                    f"SELECT gid FROM workmanship_tpl_gbop_entries "
                    f"WHERE gid IN ({placeholders}) AND node_type='process' LIMIT 500", parent_gids,
                )
                parent_map = {row["gid"]: dict(row) for row in cur.fetchall()}
            by_vpps: dict[str, list[dict[str, Any]]] = {}
            for row in operations:
                by_vpps.setdefault(str(row["vpps_part"]), []).append(row)
            bound = 0
            parts_matched = 0
            for part in parts:
                matches = by_vpps.get(str(part["vpps"]), [])
                if not matches:
                    continue
                parts_matched += 1
                for match in matches:
                    parent_gid = match.get("parent_gid") if match.get("parent_gid") in parent_map else None
                    cur.execute(
                        "INSERT INTO workmanship_bop_gbop_nav_bindings "
                        "(gid,pbom_version_gid,gbop_process_entry_gid,gbop_op_entry_gid,pbom_entry_gid,is_part_feed) "
                        "VALUES (%s,%s,%s,%s,%s,TRUE) "
                        "ON DUPLICATE KEY UPDATE gbop_process_entry_gid=VALUES(gbop_process_entry_gid),is_part_feed=TRUE",
                        (str(next_gid()), pbom_gid, parent_gid, match["entry_gid"], part["gid"]),
                    )
                    bound += 1
        conn.commit()
    return CapabilityOutput(data={"data": {"bound": bound, "parts_matched": parts_matched}})


def register_gbop_navigation_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.gbop.navigation.change.apply", owner="craft",
        description="Confirm or execute bounded GBOP/PBOM navigation auto-link changes.",
        use_when="A governed Craft consumer confirms or runs the PBOM-to-GBOP auto-link workflow.",
        do_not_use_when="The request only reads navigation projections or mutates unrelated GBOP catalog objects.",
        risk="write", confirmation="user", permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "pbom_version_gid"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "pbom_version_gid": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "gbop", "navigation", "write"),
    ), change_gbop_navigation)
