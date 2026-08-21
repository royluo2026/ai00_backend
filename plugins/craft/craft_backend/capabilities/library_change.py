"""Governed mutations for Craft's legacy manufacturing resource library."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_conn

_OPERATIONS = (
    "tools.create", "tools.update", "tools.delete", "tools.obsolete",
    "equipments.create", "equipments.update", "equipments.obsolete",
    "fixtures.create", "fixtures.update", "fixtures.obsolete",
    "fasteners.create", "fasteners.update", "fasteners.delete",
    "part_names.create", "part_names.update", "part_names.delete",
    "part_names.batch_add_from_pbom", "part_names.batch_accept_alias",
    "part_names.accept_alias",
)
_TABLES = {
    "tools": "workmanship_tpl_vpps_tools",
    "equipments": "workmanship_tpl_vpps_equipments",
    "fixtures": "workmanship_tpl_vpps_fixtures",
    "fasteners": "workmanship_tpl_fastener_spec",
    "part_names": "workmanship_tpl_vpps_parts",
}
_ALLOWED = {
    "tools": {"vpps", "name", "gun_model", "matou_part_no", "importance", "gun_type", "wireless", "output_square", "torque_min", "torque_recommended", "cad_model_no", "socket_model", "fastener_type", "fastener_params", "extension_model", "socket_cad_no", "extension_cad_no"},
    "equipments": {"name", "category", "spec"},
    "fixtures": {"name", "category", "spec"},
    "fasteners": {"fastener_type", "part_no", "name", "thread_spec", "model", "shank_length", "guide_type", "guide_length", "has_adhesive", "drive_size", "flange_diameter", "first_vehicle"},
    "part_names": {"vpps_description", "part_category", "description", "level", "vpps_desc_cn", "vpps", "importance", "vehicle_model", "parent_vpps", "status", "meta", "flex_type", "ref_main_vpps", "ref_main_vpps_desc", "ref_install_direction", "ref_static_clearance", "ref_install_clearance", "alias"},
}


def _json_value(key: str, value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False) if key in {"spec", "meta", "alias"} and isinstance(value, (dict, list)) else value


def _write_record(table_key: str, operation: str, payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    table = _TABLES[table_key]
    gid = str(payload.get("gid") or "")
    record = dict(payload.get("record") or {})
    with get_conn() as conn:
        with conn.cursor() as cur:
            if operation == "create":
                new_gid = str(next_gid())
                fields = {key: value for key, value in record.items() if key in _ALLOWED[table_key]}
                if table_key in {"equipments", "fixtures"}:
                    fields.setdefault("category", "")
                    fields.setdefault("spec", {})
                if table_key == "part_names":
                    fields.setdefault("status", "active")
                    fields.setdefault("meta", {})
                    fields.setdefault("alias", [])
                fields["gid"] = new_gid
                if context.team_gid:
                    fields["team_id"] = context.team_gid
                columns = list(fields)
                cur.execute(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
                    tuple(_json_value(key, fields[key]) for key in columns),
                )
                conn.commit()
                return {"success": True, "data": {"gid": new_gid}}
            if not gid:
                raise ValueError("gid is required")
            if operation in {"delete", "obsolete"}:
                statement = f"DELETE FROM {table} WHERE gid = %s" if operation == "delete" else f"UPDATE {table} SET status = 'obsolete' WHERE gid = %s AND status = 'active'"
                cur.execute(statement, (gid,))
                if cur.rowcount == 0:
                    raise ValueError("record not found or unavailable")
                conn.commit()
                return {"success": True}
            fields = {key: value for key, value in record.items() if key in _ALLOWED[table_key]}
            if not fields:
                return {"success": True}
            values = [_json_value(key, value) for key, value in fields.items()]
            values.append(gid)
            cur.execute(
                f"UPDATE {table} SET {', '.join(f'{key} = %s' for key in fields)} WHERE gid = %s",
                tuple(values),
            )
            if cur.rowcount == 0:
                raise ValueError("record not found")
        conn.commit()
    return {"success": True}


def change_library(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in _OPERATIONS:
        raise ValueError("unsupported Craft library change operation")
    table_key, action = operation.split(".", 1)
    if action in {"create", "update", "delete", "obsolete"}:
        return CapabilityOutput(data=_write_record(table_key, action, payload, context))
    if operation == "part_names.batch_add_from_pbom":
        added = skipped = 0
        with get_conn() as conn:
            with conn.cursor() as cur:
                for item in list(payload.get("items") or [])[:500]:
                    vpps = str(item.get("vpps") or "").strip()
                    if not vpps:
                        skipped += 1
                        continue
                    cur.execute("SELECT gid FROM workmanship_tpl_vpps_parts WHERE vpps = %s", (vpps,))
                    if cur.fetchone():
                        skipped += 1
                        continue
                    gid = str(next_gid())
                    cur.execute("INSERT INTO workmanship_tpl_vpps_parts (gid, vpps_description, vpps_desc_cn, vpps, status, meta, team_id) VALUES (%s,%s,%s,%s,%s,%s,%s)", (gid, item.get("vpps_description") or item.get("vpps_desc_cn") or "", item.get("vpps_desc_cn") or "", vpps, "有效", json.dumps(payload.get("meta") or {}, ensure_ascii=False), context.team_gid))
                    added += 1
            conn.commit()
        return CapabilityOutput(data={"success": True, "added": added, "skipped": skipped})
    if operation in {"part_names.accept_alias", "part_names.batch_accept_alias"}:
        items = list(payload.get("items") or []) if operation.endswith("batch_accept_alias") else [payload]
        processed = failed = 0
        actor = context.user_gid or "?"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with get_conn() as conn:
            with conn.cursor() as cur:
                for item in items[:500]:
                    try:
                        target = str(item.get("vpps_part_gid") or item.get("gid") or "")
                        alias = str(item.get("alias") or "")
                        if not target or not alias:
                            raise ValueError("alias target is required")
                        cur.execute("UPDATE workmanship_tpl_vpps_parts SET alias = CASE WHEN JSON_CONTAINS(alias, %s) THEN alias ELSE JSON_MERGE_PATCH(alias, %s) END WHERE gid = %s", (json.dumps([alias]), json.dumps([alias]), target))
                        if cur.rowcount == 0:
                            raise ValueError("part name not found")
                        processed += 1
                    except Exception:
                        failed += 1
            conn.commit()
        return CapabilityOutput(data={"success": True, "processed": processed, "failed": failed, "accepted_by": actor, "accepted_at": now})
    raise ValueError("unsupported Craft library change operation")


def register_craft_library_change_capability(registry: Any) -> None:
    registry.register(
        CapabilitySpec(
            id="craft.library.change.apply", owner="craft",
            description="Apply bounded, audited changes to Craft manufacturing resource library records.",
            use_when="A governed Craft consumer needs to create, update, retire, delete or reconcile library records.",
            do_not_use_when="The change belongs to BOP, PBOM, GBOP or another domain capability.",
            subject_concepts=("craft.manufacturing_resource",), effects=("write:craft.manufacturing_resource",),
            execution="cloud", risk="write", confirmation="user", plugin_callable=False,
            permissions=("craft.library.write",),
            input_schema={"type": "object", "required": ["operation"], "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)}, "gid": {"type": "string", "maxLength": 128},
                "record": {"type": "object", "maxProperties": 40, "additionalProperties": True},
                "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "maxProperties": 40, "additionalProperties": True}},
                "meta": {"type": "object", "maxProperties": 20, "additionalProperties": True}, "alias": {"type": "string", "maxLength": 500},
            }, "additionalProperties": False},
            output_schema={"type": "object", "required": ["success"], "properties": {"success": {"type": "boolean"}, "data": {"type": "object", "additionalProperties": True}, "added": {"type": "integer"}, "skipped": {"type": "integer"}, "processed": {"type": "integer"}, "failed": {"type": "integer"}, "accepted_by": {"type": "string"}, "accepted_at": {"type": "string"}}},
            tags=("craft", "library", "write"),
        ),
        change_library,
    )
