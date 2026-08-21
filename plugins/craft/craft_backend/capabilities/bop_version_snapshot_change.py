"""Governed BOP version snapshot/fork promotion."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn
from ..routers._bop._constants import _VER_COLS, _VER_KEYS
from ..routers._bop._helpers import _copy_entries_and_links, _row


OPERATIONS = ("freeze_snapshot", "promote")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _state(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value) if value else {}
        except (TypeError, ValueError):
            value = {}
    return dict(value or {})


def apply_bop_version_snapshot_change(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    version_gid = _required(payload, "version_gid")
    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        src = cur.fetchone()
        if not src:
            raise CapabilityBusinessError("resource_not_found", f"版本 {version_gid} 不存在")
        src = dict(src)
        if src.get("status") != "active":
            raise CapabilityBusinessError("invalid_state", f"只有 active 版本才能升版（当前状态：{src.get('status')}）")

        same_stage = bool(payload.get("same_stage", False)) or not payload.get("target_data_stage")
        current_stage = src.get("data_stage") or ""
        new_stage = current_stage if same_stage else str(payload.get("target_data_stage"))
        promote_to_m = bool(payload.get("promote_to_m", False)) or operation == "promote"
        snap_gid = str(next_gid())
        snap_status = "M" if promote_to_m else "baseline"
        change_note = str(payload.get("change_note") or "")
        if not change_note:
            change_note = f"升版（同阶段 {current_stage}）" if same_stage else f"升版 → {new_stage}"
        now_published = "NOW()" if promote_to_m else "NULL"
        cur.execute(
            f"""INSERT INTO workmanship_bop_bop_versions
              (gid,version_tag,bop_name,version_family_gid,project_gid,factory_gid,vehicle_model_gid,
               maturity,takt_time,version_type,pbom_version_gid,owner_gid,data_stage,parent_version_gid,
               change_note,status,frozen_at,published_at,lifecycle_phase,lifecycle_state,meta,visibility,
               created_at,updated_at)
              SELECT %s,version_tag,bop_name,version_family_gid,project_gid,factory_gid,vehicle_model_gid,
               maturity,takt_time,version_type,pbom_version_gid,owner_gid,data_stage,%s,%s,%s,NOW(),{now_published},
               lifecycle_phase,lifecycle_state,meta,visibility,NOW(),NOW()
              FROM workmanship_bop_bop_versions WHERE gid=%s""",
            (snap_gid, version_gid, change_note, snap_status, version_gid),
        )
        cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (snap_gid,))
        snap_ver = _row(cur, _VER_KEYS)
        _copy_entries_and_links(cur, version_gid, snap_gid)

        old_tag = str(src.get("version_tag") or "V1")
        if payload.get("bump_version_tag", True):
            match = re.match(r"^([A-Za-z]*)(\d+)$", old_tag)
            new_tag = f"{match.group(1)}{str(int(match.group(2)) + 1).zfill(len(match.group(2)))}" if match else f"{old_tag}+1"
        else:
            new_tag = old_tag
        lifecycle_state = _state(src.get("lifecycle_state"))
        if not same_stage:
            lifecycle_state.pop("refine_stats", None)
        cur.execute("UPDATE workmanship_bop_bop_versions SET data_stage=%s,version_tag=%s,lifecycle_state=%s,updated_at=NOW() WHERE gid=%s", (new_stage, new_tag, json.dumps(lifecycle_state, ensure_ascii=False), version_gid))
        try:
            cur.execute("UPDATE workmanship_bop_bop_version_families SET updated_at=NOW() WHERE active_version_gid=%s", (version_gid,))
        except Exception:
            pass
        conn.commit()
    return {"data": {"snapshot_gid": snap_gid, "snapshot_status": snap_status, "new_data_stage": new_stage, "new_version_tag": new_tag, "same_stage": same_stage, "snapshot": snap_ver}}


def register_bop_version_snapshot_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.version.snapshot.change.apply", owner="craft",
        description="Fork an active BOP version into a baseline or promoted immutable snapshot.",
        use_when="A governed Craft consumer freezes or promotes the current active version into a snapshot.",
        do_not_use_when="The request toggles frozen links, publishes an existing baseline, or edits draft content.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "version_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "version", "snapshot", "write"),
    ), apply_bop_version_snapshot_change)


__all__ = ["OPERATIONS", "apply_bop_version_snapshot_change", "register_bop_version_snapshot_change_capability"]
