"""Governed Craft rule-library CRUD outcomes."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from backend.platform_sdk.ids import next_display_id, next_gid

from ..data.connection import get_conn

READ_OPERATIONS = ("list", "get")
CHANGE_OPERATIONS = ("create", "update", "delete")
_FIELDS = {"code", "name", "rule_type", "enforcement_level", "status", "share_scope", "list_gid", "context_class_gid", "rule_definition", "expression"}


def _row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("created_at", "updated_at"):
        if hasattr(out.get(key), "isoformat"):
            out[key] = out[key].isoformat()
    if isinstance(out.get("rule_definition"), str):
        try:
            out["rule_definition"] = json.loads(out["rule_definition"])
        except Exception:
            out["rule_definition"] = {}
    return out


def read_rule_library(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in READ_OPERATIONS:
        raise ValueError("unsupported Craft rule library read operation")
    with get_conn() as conn:
        with conn.cursor() as cur:
            if operation == "get":
                gid = str(payload.get("gid") or "")
                if not gid:
                    raise ValueError("gid is required")
                cur.execute("SELECT * FROM workmanship_know_craft_rules WHERE gid=%s", (gid,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("rule not found")
                return CapabilityOutput(data={"success": True, "data": _row(dict(row))})
            conditions = ["(share_scope IN ('global','team') OR creator_gid=%s)"]
            params: list[Any] = [context.user_gid]
            status = payload.get("status")
            list_gid = payload.get("list_gid")
            query = payload.get("q")
            if status:
                conditions.append("status=%s"); params.append(status)
            if list_gid:
                conditions.append("list_gid=%s"); params.append(list_gid)
            if query:
                conditions.append("(name LIKE %s OR code LIKE %s)"); params.extend([f"%{query}%", f"%{query}%"])
            limit = max(1, min(int(payload.get("limit") or 200), 500))
            cur.execute(f"SELECT * FROM workmanship_know_craft_rules WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT {limit}", tuple(params))
            rows = [_row(dict(row)) for row in cur.fetchall()]
    return CapabilityOutput(data={"success": True, "data": rows})


def change_rule_library(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in CHANGE_OPERATIONS:
        raise ValueError("unsupported Craft rule library change operation")
    record = dict(payload.get("record") or {})
    gid = str(payload.get("gid") or "")
    roles = set(context.active_roles)
    is_admin = bool(roles & {"super_admin", "team_admin", "rule_admin"})
    with get_conn() as conn:
        with conn.cursor() as cur:
            if operation == "create":
                new_gid = str(next_gid())
                values = {key: record.get(key) for key in _FIELDS if key in record}
                values.setdefault("name", "")
                values.setdefault("rule_type", "process")
                values.setdefault("enforcement_level", "advisory")
                values.setdefault("status", "draft")
                values.setdefault("share_scope", "team")
                values.setdefault("rule_definition", {})
                values.update({"gid": new_gid, "display_id": f"R-C{next_display_id('rules_display_seq'):08d}", "applicable_scope": "{}", "attachments": "[]", "creator_gid": context.user_gid})
                columns = list(values)
                cur.execute(f"INSERT INTO workmanship_know_craft_rules ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})", tuple(json.dumps(values[key], ensure_ascii=False) if key in {"rule_definition", "applicable_scope", "attachments"} and not isinstance(values[key], str) else values[key] for key in columns))
                conn.commit()
                return CapabilityOutput(data={"success": True, "data": {"gid": new_gid}})
            if not gid:
                raise ValueError("gid is required")
            if operation == "delete":
                sql = "DELETE FROM workmanship_know_craft_rules WHERE gid=%s"
                params: list[Any] = [gid]
                if not is_admin:
                    sql += " AND creator_gid=%s"; params.append(context.user_gid)
                cur.execute(sql, tuple(params))
                if cur.rowcount == 0:
                    raise ValueError("rule not found or not permitted")
                conn.commit()
                return CapabilityOutput(data={"success": True})
            updates = {key: value for key, value in record.items() if key in _FIELDS}
            if not updates:
                raise ValueError("no update fields supplied")
            params = [json.dumps(value, ensure_ascii=False) if key == "rule_definition" and not isinstance(value, str) else value for key, value in updates.items()]
            params.append(gid)
            cur.execute(f"UPDATE workmanship_know_craft_rules SET {','.join(f'{key}=%s' for key in updates)},updated_at=NOW() WHERE gid=%s", tuple(params))
            if cur.rowcount == 0:
                raise ValueError("rule not found")
        conn.commit()
    return CapabilityOutput(data={"success": True})


def register_rule_library_capabilities(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.rule.library.read", owner="craft", description="Read bounded Craft rule-library records.", use_when="A governed consumer needs Craft rule definitions or search results.", do_not_use_when="The request evaluates a rule or publishes a rule release.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(READ_OPERATIONS)}, "gid": {"type": "string"}, "status": {"type": "string"}, "list_gid": {"type": "string"}, "q": {"type": "string", "maxLength": 200}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["success", "data"], "properties": {"success": {"type": "boolean"}, "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False}, tags=("craft", "rule", "library", "read")), read_rule_library)
    registry.register(CapabilitySpec(id="craft.rule.library.change.apply", owner="craft", description="Apply bounded Craft rule-library CRUD changes.", use_when="A governed consumer needs to create, update or delete a Craft rule definition.", do_not_use_when="The request evaluates a rule or changes a published rule release.", risk="write", confirmation="user", permissions=("craft.rule.write",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(CHANGE_OPERATIONS)}, "gid": {"type": "string"}, "record": {"type": "object", "maxProperties": 20, "additionalProperties": True}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["success"], "properties": {"success": {"type": "boolean"}, "data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False}, tags=("craft", "rule", "library", "write")), change_rule_library)
