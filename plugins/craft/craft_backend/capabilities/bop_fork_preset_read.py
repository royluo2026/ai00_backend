"""Bounded read projections for BOP fork presets."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn


OPERATIONS = ("list", "get")
MAX_ITEMS = 500
_COLUMNS = ("gid,name,description,include_node_types,field_rules,meta_key_rules,"
            "team_gid,created_by,created_at,updated_at")
_JSON_FIELDS = {"include_node_types", "field_rules", "meta_key_rules"}


def _parse(row: Any) -> dict[str, Any]:
    data = dict(row)
    for field in _JSON_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            try:
                data[field] = json.loads(value)
            except (TypeError, ValueError):
                pass
    return data


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def read_fork_presets(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported BOP fork preset read operation")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "get":
                gid = _required(payload, "gid")
                cur.execute(f"SELECT {_COLUMNS} FROM workmanship_bop_bop_fork_presets WHERE gid=%s", (gid,))
                row = cur.fetchone()
                if not row:
                    raise CapabilityBusinessError("resource_not_found", f"fork preset {gid} does not exist")
                return CapabilityOutput(data={"data": _parse(row)})
            team_gid = str(payload.get("team_gid") or "").strip()
            if team_gid:
                cur.execute(f"SELECT {_COLUMNS} FROM workmanship_bop_bop_fork_presets WHERE team_gid=%s OR team_gid IS NULL ORDER BY created_at LIMIT %s", (team_gid, MAX_ITEMS))
            else:
                cur.execute(f"SELECT {_COLUMNS} FROM workmanship_bop_bop_fork_presets ORDER BY created_at LIMIT %s", (MAX_ITEMS,))
            rows = [_parse(row) for row in cur.fetchall()]
    if len(rows) > MAX_ITEMS:
        raise CapabilityBusinessError("invalid_input", "fork preset result exceeds the bounded response limit", details={"limit": MAX_ITEMS})
    return CapabilityOutput(data={"data": rows})


def register_bop_fork_preset_read_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.fork_preset.read", owner="craft",
        description="Read bounded BOP fork preset projections.",
        use_when="A governed Craft consumer needs available fork presets or one preset by GID.",
        do_not_use_when="The request creates, updates, deletes, or executes a fork preset.",
        risk="read", permissions=("craft.read",),
        input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "gid": {"type": "string"}, "team_gid": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": ["array", "object"], "maxItems": MAX_ITEMS, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False},
        tags=("craft", "bop", "fork", "read"),
    ), read_fork_presets)


__all__ = ["MAX_ITEMS", "OPERATIONS", "read_fork_presets", "register_bop_fork_preset_read_capability"]
