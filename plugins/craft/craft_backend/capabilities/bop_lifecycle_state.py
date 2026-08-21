"""Read the bounded aggregate BOP lifecycle state projection."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from ..data.connection import get_craft_conn


def read_bop_lifecycle_state(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    gid = str(payload.get("version_gid") or "")
    if not gid:
        raise ValueError("version_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT lifecycle_phase,lifecycle_state,bop_name,version_tag,data_stage,version_family_gid,meta FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
            ver = cur.fetchone()
            if not ver:
                raise ValueError("BOP version not found")
            ver = dict(ver); family_gid = ver.get("version_family_gid") or gid
            cur.execute("SELECT * FROM workmanship_bop_bop_lifecycle_stats WHERE version_gid=%s AND line_gid IS NULL ORDER BY stats_snapshot_date DESC,refreshed_at DESC LIMIT 1", (gid,))
            stats_row = cur.fetchone(); stats = dict(stats_row) if stats_row else None
            cur.execute("SELECT * FROM (SELECT *,ROW_NUMBER() OVER (PARTITION BY line_gid ORDER BY stats_snapshot_date DESC,refreshed_at DESC) AS _rn FROM workmanship_bop_bop_lifecycle_stats WHERE version_gid=%s AND line_gid IS NOT NULL) _t WHERE _rn=1", (gid,))
            line_stats = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT * FROM workmanship_bop_bop_lifecycle_history WHERE version_gid=%s ORDER BY entered_at LIMIT 500", (gid,))
            history = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT gid,title FROM workmanship_bop_bop_entries WHERE version_gid=%s AND node_type='line_process' AND is_deleted=FALSE ORDER BY sort_order LIMIT 500", (gid,))
            lines = [dict(row) for row in cur.fetchall()]
            raw_meta = ver.get("meta") or {}; bop_meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
            pbom_match = bop_meta.get("pbom_match") or {}; pbom_check = {}; pbom_gid = pbom_match.get("pbom_version_gid") or ""
            if pbom_gid:
                cur.execute("SELECT meta FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_gid,))
                row = cur.fetchone()
                if row:
                    pmeta = row.get("meta") or {}; pmeta = json.loads(pmeta) if isinstance(pmeta, str) else pmeta
                    pbom_check = pmeta.get("vpps_check") or {}
            try:
                cur.execute("SELECT lifecycle_phase FROM workmanship_bop_bop_version_families WHERE gid=%s", (family_gid,))
                family_row = cur.fetchone(); family_phase = (family_row or {}).get("lifecycle_phase", "")
            except Exception:
                family_phase = ""
            try:
                cur.execute("SELECT COUNT(*) AS cnt FROM workmanship_bop_bop_pbom_diff_queue WHERE bop_version_gid=%s AND status='pending'", (gid,))
                pending = (cur.fetchone() or {}).get("cnt", 0) or 0
            except Exception:
                pending = 0
            try:
                cur.execute("SELECT gid,version_tag,bop_name,version_family_gid,data_stage,status,change_note,archived_at,frozen_at,published_at,is_deleted FROM workmanship_bop_bop_versions WHERE (version_family_gid=%s OR gid=%s) AND is_deleted=FALSE ORDER BY created_at LIMIT 500", (family_gid, family_gid))
                family_versions = [dict(row) for row in cur.fetchall()]
            except Exception:
                family_versions = []
    state = ver.get("lifecycle_state") or {}
    if isinstance(state, str):
        try: state = json.loads(state) if state else {}
        except Exception: state = {}
    return CapabilityOutput(data={"lifecycle_phase": ver.get("lifecycle_phase"), "lifecycle_state": state, "bop_name": ver.get("bop_name"), "version_tag": ver.get("version_tag"), "data_stage": ver.get("data_stage"), "version_family_gid": family_gid, "stats": stats, "line_stats": line_stats, "history": history, "lines": lines, "pbom_match": pbom_match, "pbom_vpps_check": pbom_check, "family_lifecycle_phase": family_phase, "pbom_diff_queue_pending": pending, "vehicle_ops_prep": bop_meta.get("vehicle_ops_prep", {}), "all_versions_in_family": family_versions})


def register_bop_lifecycle_state_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.bop.lifecycle.state.read", owner="craft", description="Read the bounded aggregate lifecycle state for one BOP version.", use_when="A governed consumer needs the lifecycle dashboard projection for one BOP version.", do_not_use_when="The request changes lifecycle state or refreshes lifecycle statistics.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["version_gid"], "properties": {"version_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "additionalProperties": True}, tags=("craft", "bop", "lifecycle", "read")), read_bop_lifecycle_state)
