"""Governed Standard Operation library outcomes."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from backend.platform_sdk.ids import next_display_id, next_gid

from ..data.connection import get_conn

READ_OPERATIONS = ("list", "get")
CHANGE_OPERATIONS = ("create", "update", "delete", "publish", "deprecate")
_FIELDS = (
    "code", "name", "standard_time", "importance", "description", "level", "vpps_attr",
    "vpps", "vpps_desc", "torque_importance", "vehicle_model", "parent_vpps",
    "steps", "required_tools", "parameters",
)


def _row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("created_at", "updated_at"):
        if hasattr(out.get(key), "isoformat"):
            out[key] = out[key].isoformat()
    for key in ("steps", "required_tools", "parameters"):
        if isinstance(out.get(key), str):
            try:
                out[key] = json.loads(out[key])
            except Exception:
                out[key] = [] if key != "parameters" else {}
    return out


def read_standard_operation(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in READ_OPERATIONS:
        raise ValueError("unsupported standard operation read operation")
    with get_conn() as conn:
        with conn.cursor() as cur:
            if operation == "list":
                status = payload.get("status")
                where = "WHERE (created_by = %s OR team_id = %s OR share_scope = 'global')"
                params: list[Any] = [context.user_gid, context.team_gid]
                if status:
                    where += " AND status = %s"
                    params.append(status)
                cur.execute(f"SELECT gid, display_id, code, name, status, standard_time, importance, description, level, vpps_attr, vpps, vpps_desc, torque_importance, vehicle_model, parent_vpps, share_scope, version, created_by, created_at, updated_at FROM workmanship_tpl_gbop_entries {where} ORDER BY code LIMIT 500", tuple(params))
                return CapabilityOutput(data={"items": [_row(row) for row in cur.fetchall()]})
            gid = str(payload.get("gid") or "")
            if not gid:
                raise ValueError("gid is required")
            cur.execute("SELECT gid, display_id, code, name, status, standard_time, importance, description, steps, required_tools, parameters, created_by, version, created_at, updated_at FROM workmanship_tpl_gbop_entries WHERE gid = %s", (gid,))
            row = cur.fetchone()
    if not row:
        raise ValueError("standard operation not found")
    return CapabilityOutput(data=_row(row))


def _json_value(key: str, value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False) if key in {"steps", "required_tools", "parameters"} and isinstance(value, (dict, list)) else value


def change_standard_operation(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in CHANGE_OPERATIONS:
        raise ValueError("unsupported standard operation change operation")
    gid = str(payload.get("gid") or "")
    record = dict(payload.get("record") or {})
    with get_conn() as conn:
        with conn.cursor() as cur:
            if operation == "create":
                new_gid = str(next_gid())
                values = {key: record.get(key) for key in _FIELDS if key in record}
                values.setdefault("code", "")
                values.setdefault("name", "")
                values.setdefault("standard_time", 0)
                values["gid"] = new_gid
                values["display_id"] = f"S-C{next_display_id('std_op_display_seq'):08d}"
                values["created_by"] = context.user_gid
                values["team_id"] = context.team_gid
                columns = list(values)
                cur.execute(f"INSERT INTO workmanship_tpl_gbop_entries ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})", tuple(_json_value(k, values[k]) for k in columns))
                conn.commit()
                return CapabilityOutput(data={"success": True, "gid": new_gid})
            if not gid:
                raise ValueError("gid is required")
            if operation in {"publish", "deprecate"}:
                target = "active" if operation == "publish" else "deprecated"
                source = "draft" if operation == "publish" else "active"
                cur.execute("UPDATE workmanship_tpl_gbop_entries SET status=%s, updated_at=NOW() WHERE gid=%s AND status=%s", (target, gid, source))
                if cur.rowcount == 0:
                    raise ValueError("standard operation not found or lifecycle state is invalid")
                conn.commit()
                return CapabilityOutput(data={"success": True, "gid": gid})
            if operation == "delete":
                cur.execute("DELETE FROM workmanship_tpl_gbop_entries WHERE gid=%s AND (created_by=%s OR team_id=%s)", (gid, context.user_gid, context.team_gid))
                if cur.rowcount == 0:
                    raise ValueError("standard operation not found or not owned")
                conn.commit()
                return CapabilityOutput(data={"success": True, "gid": gid})
            updates = {key: value for key, value in record.items() if key in _FIELDS and value is not None}
            if not updates:
                raise ValueError("no update fields supplied")
            updates["version"] = "version + 1"
            updates["updated_at"] = "NOW()"
            assignments = []
            params: list[Any] = []
            for key, value in updates.items():
                if key in {"version", "updated_at"}:
                    assignments.append(f"{key} = {value}")
                else:
                    assignments.append(f"{key} = %s")
                    params.append(_json_value(key, value))
            params.extend([gid, context.user_gid, context.team_gid])
            cur.execute(f"UPDATE workmanship_tpl_gbop_entries SET {', '.join(assignments)} WHERE gid=%s AND (created_by=%s OR team_id=%s)", tuple(params))
            if cur.rowcount == 0:
                raise ValueError("standard operation not found or not owned")
        conn.commit()
    return CapabilityOutput(data={"success": True, "gid": gid})


def register_standard_operation_capabilities(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.standard_operation.read", owner="craft", description="Read bounded Craft standard operation library records.", use_when="A governed consumer needs standard operation definitions.", do_not_use_when="The outcome is a GBOP release or BOP execution operation.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(READ_OPERATIONS)}, "gid": {"type": "string"}, "status": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "properties": {"items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "gid": {"type": "string"}, "data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False}, tags=("craft", "standard_operation", "read")), read_standard_operation)
    registry.register(CapabilitySpec(id="craft.standard_operation.change.apply", owner="craft", description="Apply bounded Craft standard operation lifecycle and content changes.", use_when="A governed consumer needs to create, update, publish, deprecate or delete a standard operation.", do_not_use_when="The change belongs to a GBOP release or BOP execution operation.", risk="write", confirmation="user", permissions=("craft.write",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(CHANGE_OPERATIONS)}, "gid": {"type": "string"}, "record": {"type": "object", "maxProperties": 30, "additionalProperties": True}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["success", "gid"], "properties": {"success": {"type": "boolean"}, "gid": {"type": "string"}}, "additionalProperties": False}, tags=("craft", "standard_operation", "write")), change_standard_operation)
