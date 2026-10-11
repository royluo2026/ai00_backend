"""Read operation CATIA occurrence names below a BOP line entry."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from ..data.connection import get_craft_conn
from ..services.bop_picture_refs import normalize_bop_pictures


def read_bop_line_operation_catia(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    line_gid = str(payload.get("line_entry_gid") or "")
    if not line_gid:
        raise ValueError("line_entry_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "WITH RECURSIVE desc_entries AS ("
                "SELECT gid,title,sort_order,node_type,parent_gid,process_flow_pic,version_gid FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted=FALSE "
                "UNION ALL SELECT b.gid,b.title,b.sort_order,b.node_type,b.parent_gid,b.process_flow_pic,b.version_gid FROM workmanship_bop_bop_entries b JOIN desc_entries d ON b.parent_gid=d.gid AND b.version_gid=d.version_gid WHERE b.is_deleted=FALSE) "
                "SELECT d.gid AS bop_entry_gid,d.title,d.sort_order,d.node_type,d.parent_gid,d.process_flow_pic,IFNULL(JSON_ARRAYAGG(CASE WHEN p.catia_occurrence_name IS NOT NULL AND p.catia_occurrence_name != '' THEN p.catia_occurrence_name END),JSON_ARRAY()) AS catia_names "
                "FROM desc_entries d LEFT JOIN workmanship_bop_bop_entry_links bel ON bel.entry_gid=d.gid AND bel.link_type='pbom_part' AND bel.deleted_at IS NULL "
                "LEFT JOIN workmanship_bop_pbom p ON p.gid=bel.entity_gid WHERE d.node_type IN ('process','bop_process','operation','bop_operation','bop_steps','step') GROUP BY d.gid,d.title,d.sort_order,d.node_type,d.parent_gid,d.process_flow_pic ORDER BY d.sort_order DESC,d.gid DESC LIMIT 500",
                (line_gid,),
            )
            rows = cur.fetchall()
    data = []
    for row in rows:
        names = row["catia_names"]
        if isinstance(names, str):
            names = json.loads(names)
        data.append({
            "bop_entry_gid": row["bop_entry_gid"], "title": row["title"] or "",
            "sort_order": row["sort_order"], "node_type": row.get("node_type"),
            "parent_gid": row.get("parent_gid"),
            "process_flow_pic": normalize_bop_pictures(row.get("process_flow_pic")),
            "catia_names": [name for name in (names or []) if name],
        })
    return CapabilityOutput(data={"ok": True, "data": data})


def register_bop_line_operation_catia_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.bop.line_operation_catia.read", owner="craft", description="Read bounded operation CATIA occurrence names below one BOP line entry.", use_when="A governed consumer needs operation-level CATIA occurrence names for one BOP line.", do_not_use_when="The request mutates BOP entries or needs a complete execution structure.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["line_entry_gid"], "properties": {"line_entry_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["ok", "data"], "properties": {"ok": {"type": "boolean"}, "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False}, tags=("craft", "bop", "catia", "read")), read_bop_line_operation_catia)
