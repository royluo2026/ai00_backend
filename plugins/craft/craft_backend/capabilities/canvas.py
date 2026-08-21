"""Governed Craft canvas read/change outcomes."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_conn


def _row(row: dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    if hasattr(value.get("updated_at"), "isoformat"):
        value["updated_at"] = value["updated_at"].isoformat()
    if isinstance(value.get("data"), str):
        try:
            value["data"] = json.loads(value["data"])
        except Exception:
            value["data"] = {}
    return value


def read_canvas(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = payload.get("operation")
    if operation not in {"list", "get"}:
        raise ValueError("unsupported Craft canvas read operation")
    with get_conn() as conn:
        with conn.cursor() as cur:
            if operation == "list":
                cur.execute("SELECT gid, owner_gid, title, is_shared, updated_at FROM workmanship_app_wfc_canvases WHERE owner_gid = %s OR is_shared = TRUE ORDER BY updated_at DESC LIMIT 500", (context.user_gid,))
                return CapabilityOutput(data={"items": [_row(row) for row in cur.fetchall()]})
            gid = str(payload.get("gid") or "")
            if not gid:
                raise ValueError("gid is required")
            cur.execute("SELECT gid, owner_gid, title, data, is_shared, updated_at FROM workmanship_app_wfc_canvases WHERE gid = %s", (gid,))
            row = cur.fetchone()
    if not row:
        raise ValueError("canvas not found")
    return CapabilityOutput(data=_row(row))


def change_canvas(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = payload.get("operation")
    if operation not in {"save", "delete", "toggle_shared"}:
        raise ValueError("unsupported Craft canvas change operation")
    gid = str(payload.get("gid") or "")
    with get_conn() as conn:
        with conn.cursor() as cur:
            if operation == "save":
                record = dict(payload.get("record") or {})
                title = str(record.get("title") or "未命名画布")
                data = record.get("data") or {}
                shared = bool(record.get("is_shared", False))
                if gid:
                    cur.execute("UPDATE workmanship_app_wfc_canvases SET title=%s, data=%s, is_shared=%s, updated_at=NOW() WHERE gid=%s AND owner_gid=%s", (title, json.dumps(data, ensure_ascii=False), shared, gid, context.user_gid))
                    if cur.rowcount == 0:
                        raise ValueError("canvas not found or not owned")
                else:
                    gid = str(next_gid())
                    cur.execute("INSERT INTO workmanship_app_wfc_canvases (gid, owner_gid, title, data, is_shared) VALUES (%s,%s,%s,%s,%s)", (gid, context.user_gid, title, json.dumps(data, ensure_ascii=False), shared))
            elif operation == "delete":
                cur.execute("DELETE FROM workmanship_app_wfc_canvases WHERE gid=%s AND owner_gid=%s", (gid, context.user_gid))
                if cur.rowcount == 0:
                    raise ValueError("canvas not found or not owned")
            else:
                shared = bool((payload.get("record") or {}).get("is_shared", False))
                cur.execute("UPDATE workmanship_app_wfc_canvases SET is_shared=%s, updated_at=NOW() WHERE gid=%s AND owner_gid=%s", (shared, gid, context.user_gid))
                if cur.rowcount == 0:
                    raise ValueError("canvas not found or not owned")
            conn.commit()
    return CapabilityOutput(data={"success": True, "gid": gid})


def register_canvas_capabilities(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.canvas.read", owner="craft", description="Read owned and shared Craft canvases.", use_when="A governed consumer needs Craft canvas state.", do_not_use_when="The object is a BOP execution canvas.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": ["list", "get"]}, "gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "additionalProperties": True}, tags=("craft", "canvas", "read")), read_canvas)
    registry.register(CapabilitySpec(id="craft.canvas.change.apply", owner="craft", description="Create, update, delete or share Craft canvases.", use_when="A governed consumer needs a scoped Craft canvas mutation.", do_not_use_when="The change belongs to a BOP execution canvas.", risk="write", confirmation="user", permissions=("craft.write",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": ["save", "delete", "toggle_shared"]}, "gid": {"type": "string"}, "record": {"type": "object", "maxProperties": 10, "additionalProperties": True}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["success", "gid"], "properties": {"success": {"type": "boolean"}, "gid": {"type": "string"}}}, tags=("craft", "canvas", "write")), change_canvas)
