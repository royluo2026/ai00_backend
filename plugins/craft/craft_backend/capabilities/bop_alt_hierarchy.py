"""Read the bounded BOP alternative hierarchy with linked PBOM occurrence data."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn


def read_bop_alt_hierarchy(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    version_gid = str(payload.get("version_gid") or "")
    if not version_gid:
        raise ValueError("version_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT e.gid,e.parent_gid,e.node_type,e.sort_order,e.title,e.vpps,e.level,e.ai00_level, "
                "p.gid AS part_gid,p.part_no,p.catia_occurrence_name,p.title AS part_name,p.vpps AS part_vpps,p.quantity "
                "FROM workmanship_bop_bop_entries e "
                "LEFT JOIN workmanship_bop_bop_entry_links l ON l.entry_gid=e.gid AND l.link_type='pbom_part' "
                "LEFT JOIN workmanship_bop_pbom p ON p.gid=l.entity_gid "
                "WHERE e.version_gid=%s AND e.is_deleted=FALSE ORDER BY e.sort_order LIMIT 1000",
                (version_gid,),
            )
            entries: dict[Any, dict[str, Any]] = {}
            for row in cur.fetchall():
                item = dict(row); gid = item["gid"]
                entry = entries.setdefault(gid, {"gid": gid, "parent_gid": item.get("parent_gid"), "node_type": item.get("node_type"), "sort_order": item.get("sort_order"), "title": item.get("title"), "vpps": item.get("vpps"), "level": item.get("level"), "ai00_level": item.get("ai00_level"), "parts": []})
                if item.get("part_gid"):
                    entry["parts"].append({"gid": item["part_gid"], "part_no": item.get("part_no") or "", "catia_occ": item.get("catia_occurrence_name") or "", "name": item.get("part_name") or "", "vpps": item.get("part_vpps") or "", "quantity": item.get("quantity")})
    return CapabilityOutput(data={"entries": list(entries.values())})


def register_bop_alt_hierarchy_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.bop.alt_hierarchy.read", owner="craft", description="Read a bounded BOP hierarchy enriched with linked PBOM CATIA occurrences.", use_when="A governed consumer needs the alternative hierarchy projection for one BOP version.", do_not_use_when="The consumer needs to mutate entries or read revision-pinned navigation contracts.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["version_gid"], "properties": {"version_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["entries"], "properties": {"entries": {"type": "array", "maxItems": 1000, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False}, tags=("craft", "bop", "hierarchy", "read")), read_bop_alt_hierarchy)
