"""Governed BOP lifecycle init-state and phase confirmation changes."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn


OPERATIONS = ("init.update", "phase.confirm")
_NEXT_PHASE = {"init": "refine", "refine": "publish_cycle", "publish_cycle": "archived"}


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


def apply_bop_lifecycle_state_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    version_gid = _required(payload, "version_gid")

    with get_craft_conn() as conn, conn.cursor() as cur:
        if operation == "init.update":
            cur.execute("SELECT lifecycle_state FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
            row = cur.fetchone()
            if not row:
                raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
            state = _state(row.get("lifecycle_state") if isinstance(row, dict) else dict(row)["lifecycle_state"])
            init = _state(state.get("init"))
            if "route" in payload:
                if payload["route"] is None:
                    init.pop("route", None)
                else:
                    init["route"] = payload["route"]
            if "checklist" in payload and payload["checklist"] is not None:
                checklist = payload["checklist"]
                if not isinstance(checklist, dict):
                    raise ValueError("checklist must be an object")
                init["checklist"] = {**_state(init.get("checklist")), **checklist} if checklist else {}
            state["init"] = init
            cur.execute("UPDATE workmanship_bop_bop_versions SET lifecycle_state=%s,updated_at=NOW() WHERE gid=%s", (json.dumps(state, ensure_ascii=False), version_gid))
            conn.commit()
            return {"data": {"lifecycle_state": state}}

        note = payload.get("note")
        cur.execute("SELECT lifecycle_phase FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
        current = (row.get("lifecycle_phase") if isinstance(row, dict) else dict(row)["lifecycle_phase"]) or ""
        next_phase = _NEXT_PHASE.get(current)
        if not next_phase:
            raise CapabilityBusinessError("invalid_state", f"lifecycle phase {current} cannot advance")
        user_gid = context.user_gid
        cur.execute(
            "INSERT INTO workmanship_bop_bop_lifecycle_history (gid,version_gid,phase,entered_at,confirmed_at,confirmed_by_gid,confirmed_by_name,note) VALUES (%s,%s,%s,NOW(),NOW(),%s,%s,%s) ON DUPLICATE KEY UPDATE confirmed_at=NOW(),confirmed_by_gid=%s,confirmed_by_name=%s,note=%s",
            [str(next_gid()), version_gid, current, user_gid, user_gid, note, user_gid, user_gid, note],
        )
        cur.execute("INSERT IGNORE INTO workmanship_bop_bop_lifecycle_history (gid,version_gid,phase,entered_at) VALUES (%s,%s,%s,NOW())", (str(next_gid()), version_gid, next_phase))
        cur.execute("UPDATE workmanship_bop_bop_versions SET lifecycle_phase=%s,updated_at=NOW() WHERE gid=%s", (next_phase, version_gid))
        conn.commit()
    return {"data": {"lifecycle_phase": next_phase}}


def register_bop_lifecycle_state_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.lifecycle.state.change.apply", owner="craft",
        description="Update BOP lifecycle initialization state or confirm and advance its current phase.",
        use_when="A governed Craft consumer changes initialization checklist/route or confirms the current lifecycle phase.",
        do_not_use_when="The request refreshes metrics, creates/restores checkpoints, or undoes/redoes history.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "version_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "lifecycle", "state", "write"),
    ), apply_bop_lifecycle_state_change)


__all__ = ["OPERATIONS", "apply_bop_lifecycle_state_change", "register_bop_lifecycle_state_change_capability"]
