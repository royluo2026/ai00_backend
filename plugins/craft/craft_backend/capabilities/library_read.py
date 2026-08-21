"""Governed read access for Craft's legacy manufacturing resource library."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilitySpec, CapabilityOutput, CapabilityContext

from ..data.connection import get_conn

_OPERATIONS = ("tools.list", "equipments.list", "fixtures.list", "fasteners.list", "part_names.list")
_ITEMS = {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}


def _transport(row: dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    for key, item in list(value.items()):
        if hasattr(item, "isoformat"):
            value[key] = item.isoformat()
        elif key in {"meta", "alias", "spec"} and isinstance(item, str):
            try:
                value[key] = json.loads(item)
            except Exception:
                value[key] = {} if key in {"meta", "spec"} else []
    return value


def read_library(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = payload.get("operation")
    if operation not in _OPERATIONS:
        raise ValueError("unsupported Craft library read operation")
    query = str(payload.get("q") or "")[:200]
    statements = {
        "tools.list": (
            "SELECT gid,vpps,name,gun_model,matou_part_no,importance,gun_type,wireless,output_square,"
            "torque_min,torque_recommended,cad_model_no,socket_model,fastener_type,fastener_params,"
            "extension_model,socket_cad_no,extension_cad_no,status,created_at "
            "FROM workmanship_tpl_vpps_tools ORDER BY created_at DESC LIMIT 500", None,
        ),
        "equipments.list": (
            "SELECT gid,name,category,status,spec,created_at FROM workmanship_tpl_vpps_equipments "
            "ORDER BY created_at DESC LIMIT 500", None,
        ),
        "fixtures.list": (
            "SELECT gid,name,category,status,spec,created_at FROM workmanship_tpl_vpps_fixtures "
            "ORDER BY created_at DESC LIMIT 500", None,
        ),
        "fasteners.list": (
            "SELECT gid,fastener_type,part_no,name,thread_spec,model,shank_length,guide_type,guide_length,"
            "has_adhesive,drive_size,flange_diameter,first_vehicle,status,created_at "
            "FROM workmanship_tpl_fastener_spec ORDER BY created_at DESC LIMIT 500", None,
        ),
        "part_names.list": (
            "SELECT gid,vpps_description,part_category,description,level,vpps_desc_cn,vpps,importance,"
            "vehicle_model,parent_vpps,status,meta,flex_type,ref_main_vpps,ref_main_vpps_desc,"
            "ref_install_direction,ref_static_clearance,ref_install_clearance,alias,created_at "
            "FROM workmanship_tpl_vpps_parts "
            + ("WHERE vpps_description LIKE %s " if query else "")
            + "ORDER BY vpps_description LIMIT 500", (f"%{query}%",) if query else None,
        ),
    }
    statement, params = statements[operation]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params or ())
            rows = [_transport(dict(row)) for row in cur.fetchall()]
    return CapabilityOutput(data={"items": rows, "total": len(rows), "operation": operation})


def register_craft_library_read_capability(registry: Any) -> None:
    registry.register(
        CapabilitySpec(
            id="craft.library.read",
            owner="craft",
            description="Read bounded Craft manufacturing resource library collections.",
            use_when="A governed consumer needs Craft tool, equipment, fixture, fastener or standard part-name records.",
            do_not_use_when="The caller needs to mutate library records or read BOP-linked resources.",
            subject_concepts=("craft.manufacturing_resource",),
            effects=("read:craft.manufacturing_resource",),
            execution="cloud",
            risk="read",
            confirmation="none",
            plugin_callable=False,
            input_schema={
                "type": "object", "required": ["operation"],
                "properties": {
                    "operation": {"type": "string", "enum": list(_OPERATIONS)},
                    "q": {"type": "string", "maxLength": 200},
                }, "additionalProperties": False,
            },
            output_schema={
                "type": "object", "required": ["items", "total", "operation"],
                "properties": {"items": _ITEMS, "total": {"type": "integer", "minimum": 0, "maximum": 500}, "operation": {"type": "string"}},
            },
            tags=("craft", "library", "read"),
        ),
        read_library,
    )
