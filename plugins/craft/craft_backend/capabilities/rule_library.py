"""Governed Craft rule-library CRUD outcomes."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from backend.platform_sdk.ids import next_display_id, next_gid

from ..application.rules import (
    MysqlRuleDefinitionRepository,
    RULE_DEFINITION_FIELDS,
    canonical_rule_definition_command,
    validate_rule_definition_changes,
)
from ..data.connection import get_conn

READ_OPERATIONS = ("list", "get")
CHANGE_OPERATIONS = ("create", "update", "delete")
_FIELDS = {"code", "name", "rule_type", "enforcement_level", "status", "share_scope", "list_gid", "context_class_gid", "rule_definition", "expression"}
RULE_DEFINITION_INPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "rule_gid": {"type": "string", "minLength": 1, "maxLength": 255},
        "expected_revision": {"type": "integer", "minimum": 1},
        "changes": {
            "type": "object", "minProperties": 1, "maxProperties": len(RULE_DEFINITION_FIELDS), "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 2000},
                "description": {"type": "string", "minLength": 1, "maxLength": 2000},
                "severity": {"type": "string", "minLength": 1, "maxLength": 64},
                "enabled": {"type": "boolean"},
                "condition": {"type": "string", "minLength": 1, "maxLength": 1024},
                "message": {"type": "string", "minLength": 1, "maxLength": 2000},
                "scope": {"type": "string", "minLength": 1, "maxLength": 128},
                "tags": {"type": "array", "maxItems": 32, "items": {"type": "string", "minLength": 1, "maxLength": 128}},
                "priority": {"type": "integer", "minimum": 0, "maximum": 100},
                "category": {"type": "string", "minLength": 1, "maxLength": 128},
            },
        },
    },
    "required": ["rule_gid", "expected_revision", "changes"],
}
RULE_DEFINITION_OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "rule_gid": {"type": "string", "minLength": 1, "maxLength": 255}, "revision": {"type": "integer", "minimum": 1, "maximum": 2147483647},
        "name": {"type": "string", "maxLength": 2000}, "description": {"type": "string", "maxLength": 2000}, "severity": {"type": "string", "maxLength": 64}, "enabled": {"type": "boolean"}, "condition": {"type": "string", "maxLength": 1024},
        "message": {"type": "string", "maxLength": 2000}, "scope": {"type": "string", "maxLength": 128}, "tags": {"type": "array", "maxItems": 32, "items": {"type": "string", "minLength": 1, "maxLength": 128}}, "priority": {"type": "integer", "minimum": 0, "maximum": 100}, "category": {"type": "string", "maxLength": 128},
    },
    "required": ["rule_gid", "revision", *sorted(RULE_DEFINITION_FIELDS)],
}
rule_definition_repository = MysqlRuleDefinitionRepository()


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


def change_rule_definition(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    """Apply exactly one owner-authorized, revision-pinned rule definition change."""
    changes = validate_rule_definition_changes(payload.get("changes"))
    rule_gid = str(payload.get("rule_gid") or "")
    expected_revision = payload.get("expected_revision")
    idempotency_key = str(getattr(context, "idempotency_key", "") or "")
    if not rule_gid or not isinstance(expected_revision, int) or expected_revision < 1:
        raise ValueError("invalid rule definition command")
    if not idempotency_key:
        from backend.capability_v2.provider_contracts import CapabilityBusinessError
        raise CapabilityBusinessError("idempotency_key_required", "Rule definition changes require an idempotency key.")
    return CapabilityOutput(data=rule_definition_repository.change(
        rule_gid=rule_gid, expected_revision=expected_revision, changes=changes,
        actor_gid=context.user_gid, team_gid=context.team_gid, idempotency_key=idempotency_key,
        command_digest=canonical_rule_definition_command({"rule_gid": rule_gid, "expected_revision": expected_revision, "changes": changes}),
    ))


def register_rule_definition_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.rule.definition.change.apply", owner="craft",
        description="Apply one closed, revision-pinned Craft rule definition change.",
        use_when="A governed consumer changes an owned Craft rule definition.",
        do_not_use_when="The caller supplies rule source, compiled artifacts, ownership, or audit fields.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.rule.write",),
        input_schema=RULE_DEFINITION_INPUT_SCHEMA, output_schema=RULE_DEFINITION_OUTPUT_SCHEMA,
        tags=("craft", "rule", "definition", "write"),
    ), change_rule_definition)


def register_rule_library_capabilities(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.rule.library.read", owner="craft", description="Read bounded Craft rule-library records.", use_when="A governed consumer needs Craft rule definitions or search results.", do_not_use_when="The request evaluates a rule or publishes a rule release.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(READ_OPERATIONS)}, "gid": {"type": "string"}, "status": {"type": "string"}, "list_gid": {"type": "string"}, "q": {"type": "string", "maxLength": 200}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["success", "data"], "properties": {"success": {"type": "boolean"}, "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False}, tags=("craft", "rule", "library", "read")), read_rule_library)
    registry.register(CapabilitySpec(id="craft.rule.library.change.apply", owner="craft", description="Apply bounded Craft rule-library CRUD changes.", use_when="A governed consumer needs to create, update or delete a Craft rule definition.", do_not_use_when="The request evaluates a rule or changes a published rule release.", risk="write", confirmation="user", permissions=("craft.rule.write",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(CHANGE_OPERATIONS)}, "gid": {"type": "string"}, "record": {"type": "object", "maxProperties": 20, "additionalProperties": True}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["success"], "properties": {"success": {"type": "boolean"}, "data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False}, tags=("craft", "rule", "library", "write")), change_rule_library)
    register_rule_definition_change_capability(registry)
