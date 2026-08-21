"""Bounded read access to Craft GBOP catalog collections."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn

OPERATIONS = ("entries.list", "processes.list", "operations.list", "entry_links.list")


def _transport(row: dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    for key, item in list(value.items()):
        if hasattr(item, "isoformat"):
            value[key] = item.isoformat()
        elif key in {"meta", "steps", "required_tools", "parameters"} and isinstance(item, str):
            try:
                value[key] = json.loads(item)
            except Exception:
                value[key] = {} if key in {"meta", "parameters"} else []
    return value


def read_gbop_catalog(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported GBOP catalog operation")
    version_gid = str(payload.get("version_gid") or "")
    entry_gid = str(payload.get("entry_gid") or "")
    if operation != "entry_links.list" and not version_gid:
        raise ValueError("version_gid is required")
    if operation == "entry_links.list" and not entry_gid:
        raise ValueError("entry_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "entries.list":
                cur.execute("SELECT * FROM workmanship_tpl_gbop_entries WHERE version_gid=%s ORDER BY seq_no, created_at LIMIT 500", (version_gid,))
                entries = [_transport(dict(row)) for row in cur.fetchall()]
                cur.execute("SELECT * FROM workmanship_tpl_gbop_entry_links WHERE entry_gid IN (SELECT gid FROM workmanship_tpl_gbop_entries WHERE version_gid=%s) ORDER BY created_at LIMIT 500", (version_gid,))
                links: dict[str, list[dict[str, Any]]] = {}
                for row in cur.fetchall():
                    item = _transport(dict(row)); links.setdefault(str(item.get("entry_gid")), []).append(item)
                for item in entries:
                    item["links"] = links.get(str(item.get("gid")), [])
                return CapabilityOutput(data={"items": entries, "total": len(entries), "operation": operation})
            if operation == "processes.list":
                cur.execute("SELECT * FROM workmanship_tpl_gbop_processes WHERE version_gid=%s ORDER BY created_at LIMIT 500", (version_gid,))
            elif operation == "operations.list":
                cur.execute("SELECT * FROM workmanship_tpl_gbop_operations WHERE version_gid=%s ORDER BY created_at LIMIT 500", (version_gid,))
            else:
                cur.execute("SELECT * FROM workmanship_tpl_gbop_entry_links WHERE entry_gid=%s ORDER BY created_at LIMIT 500", (entry_gid,))
            rows = [_transport(dict(row)) for row in cur.fetchall()]
    return CapabilityOutput(data={"items": rows, "total": len(rows), "operation": operation})


def register_gbop_catalog_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.gbop.catalog.read", owner="craft", description="Read bounded GBOP entries, processes, operations and entry links.", use_when="A governed consumer needs GBOP catalog state for a specific version or entry.", do_not_use_when="The request mutates GBOP state or imports/forks a version.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "version_gid": {"type": "string"}, "entry_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["items", "total", "operation"], "properties": {"items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "total": {"type": "integer", "minimum": 0, "maximum": 500}, "operation": {"type": "string"}}, "additionalProperties": False}, tags=("craft", "gbop", "catalog", "read")), read_gbop_catalog)
