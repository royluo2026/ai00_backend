"""Governed refresh of persisted BOP lifecycle statistics snapshots."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _value(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, dict) else dict(row).get(key)


def apply_bop_lifecycle_stats_refresh(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    version_gid = _required(payload, "version_gid")
    # Runtime import avoids importing the router at provider registration time.
    from ..routers._bop.lifecycle import _compute_stats

    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        if not cur.fetchone():
            raise CapabilityBusinessError("resource_not_found", f"版本 {version_gid} 不存在")
        cur.execute("SELECT gid FROM workmanship_bop_bop_entries WHERE version_gid=%s AND node_type='line_process' AND is_deleted=FALSE", (version_gid,))
        line_gids = [str(_value(row, "gid")) for row in cur.fetchall() if _value(row, "gid")]
        cur.execute("SELECT meta FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        meta_row = cur.fetchone()
        raw_meta = _value(meta_row, "meta") if meta_row else None
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) and raw_meta else (raw_meta or {})
        pbom_version_gid = (meta or {}).get("pbom_match", {}).get("pbom_version_gid", "")
        nok_vpps = 0
        if pbom_version_gid:
            cur.execute("SELECT meta FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_version_gid,))
            pbom_row = cur.fetchone()
            pbom_meta = _value(pbom_row, "meta") if pbom_row else {}
            if isinstance(pbom_meta, str):
                try:
                    pbom_meta = json.loads(pbom_meta)
                except (TypeError, ValueError):
                    pbom_meta = {}
            nok_vpps = (pbom_meta or {}).get("vpps_check", {}).get("nok", 0) or 0

        for line_gid in [None, *line_gids]:
            stats = _compute_stats(cur, version_gid, line_gid)
            if line_gid is None and nok_vpps:
                stats["nok_vpps"] = nok_vpps
            values = (
                str(next_gid()), version_gid, line_gid, date.today().isoformat(),
                stats["nok_vpps"], stats["nok_unbound_parts"], stats["nok_unbound_ops"],
                stats["tools_bound"], stats["tools_total"], stats["fixtures_bound"], stats["fixtures_total"],
                stats["equipment_bound"], stats["equipment_total"], stats["coverage_ok"], stats["balance_ok"],
                stats["tasks_done"], stats["tasks_total"], stats["issues_open"], stats["rules_warn"], stats["rules_block"],
            )
            cur.execute(
                """INSERT INTO workmanship_bop_bop_lifecycle_stats
                  (gid,version_gid,line_gid,stats_snapshot_date,nok_vpps,nok_unbound_parts,nok_unbound_ops,
                   tools_bound,tools_total,fixtures_bound,fixtures_total,equipment_bound,equipment_total,
                   coverage_ok,balance_ok,tasks_done,tasks_total,issues_open,rules_warn,rules_block,refreshed_at)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                  ON DUPLICATE KEY UPDATE nok_vpps=VALUES(nok_vpps),nok_unbound_parts=VALUES(nok_unbound_parts),
                   nok_unbound_ops=VALUES(nok_unbound_ops),tools_bound=VALUES(tools_bound),tools_total=VALUES(tools_total),
                   fixtures_bound=VALUES(fixtures_bound),fixtures_total=VALUES(fixtures_total),equipment_bound=VALUES(equipment_bound),
                   equipment_total=VALUES(equipment_total),coverage_ok=VALUES(coverage_ok),balance_ok=VALUES(balance_ok),
                   tasks_done=VALUES(tasks_done),tasks_total=VALUES(tasks_total),issues_open=VALUES(issues_open),
                   rules_warn=VALUES(rules_warn),rules_block=VALUES(rules_block),refreshed_at=NOW()""",
                values,
            )
        conn.commit()
    return {"data": {"accepted": True, "version_gid": version_gid, "refreshed_lines": len(line_gids) + 1}}


def register_bop_lifecycle_stats_refresh_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.lifecycle.stats.refresh.apply", owner="craft",
        description="Recompute and persist the current BOP lifecycle statistics snapshot.",
        use_when="A governed Craft consumer explicitly requests a fresh lifecycle metrics snapshot.",
        do_not_use_when="The request only reads lifecycle state or changes a lifecycle resource.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["version_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "lifecycle", "stats", "write"),
    ), apply_bop_lifecycle_stats_refresh)


__all__ = ["apply_bop_lifecycle_stats_refresh", "register_bop_lifecycle_stats_refresh_capability"]
