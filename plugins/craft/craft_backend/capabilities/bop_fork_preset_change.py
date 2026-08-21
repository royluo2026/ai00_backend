"""Governed CRUD for BOP fork presets."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn


_COLUMNS = "gid,name,description,include_node_types,field_rules,meta_key_rules,team_gid,created_by,created_at,updated_at"
_JSON_FIELDS = {"include_node_types", "field_rules", "meta_key_rules"}
_UPDATE_FIELDS = {"name", "description", "include_node_types", "field_rules", "meta_key_rules", "team_gid"}


def _parse(row: Any) -> dict[str, Any]:
    result = dict(row)
    for field in _JSON_FIELDS:
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            try:
                result[field] = json.loads(value)
            except (TypeError, ValueError):
                pass
    return result


def apply_fork_preset_change(payload: dict[str, Any], context: CapabilityContext):
    operation = str(payload.get("operation") or "").strip()
    if operation == "create":
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        gid = str(next_gid())
        with get_craft_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_fork_presets "
                    "(gid,name,description,include_node_types,field_rules,meta_key_rules,team_gid,created_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (gid, name, payload.get("description"), json.dumps(payload.get("include_node_types")),
                     json.dumps(payload.get("field_rules") or {}), json.dumps(payload.get("meta_key_rules") or {}),
                     payload.get("team_gid"), context.user_gid),
                )
                cur.execute(f"SELECT {_COLUMNS} FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
                row = cur.fetchone()
            conn.commit()
        return {"data": _parse(row) if row else {"gid": gid}}

    gid = str(payload.get("gid") or "").strip()
    if not gid:
        raise ValueError("gid is required")
    if operation == "update":
        updates = payload.get("updates")
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty object")
        unknown = set(updates) - _UPDATE_FIELDS
        if unknown:
            raise ValueError(f"unsupported update fields: {', '.join(sorted(unknown))}")
        assignments, values = [], []
        for field, value in updates.items():
            assignments.append(f"{field}=%s")
            values.append(json.dumps(value) if field in _JSON_FIELDS else value)
        assignments.append("updated_at=NOW()")
        with get_craft_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_bop_bop_fork_presets SET {', '.join(assignments)} WHERE gid=%s", values + [gid])
                cur.execute(f"SELECT {_COLUMNS} FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"fork preset {gid} does not exist")
        return {"data": _parse(row)}

    if operation == "delete":
        with get_craft_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
                deleted = cur.rowcount
            conn.commit()
        if not deleted:
            raise CapabilityBusinessError("resource_not_found", f"fork preset {gid} does not exist")
        return {"data": {"gid": gid, "deleted": True}}
    raise ValueError("operation must be one of: create, update, delete")


def register_bop_fork_preset_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.fork_preset.change.apply", owner="craft",
        description="Create, update, or delete a BOP fork preset.",
        use_when="A governed Craft consumer changes fork-preset metadata.",
        do_not_use_when="The request forks a BOP version or mutates BOP entries.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": False},
        tags=("craft", "bop", "fork", "write"),
    ), apply_fork_preset_change)


__all__ = ["apply_fork_preset_change", "register_bop_fork_preset_change_capability"]
