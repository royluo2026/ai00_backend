"""Bounded compatibility reads for legacy BOP version projections."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from ..data.connection import get_craft_conn

OPERATIONS = ("layout_config", "bop_tree", "station_part_map")


def read_bop_version_legacy(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    gid = str(payload.get("version_gid") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported BOP version read operation")
    if not gid:
        raise ValueError("version_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "layout_config":
                cur.execute("SELECT JSON_EXTRACT(meta,'$.view_config') AS cfg FROM workmanship_bop_bop_versions WHERE gid=%s", (gid,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("BOP version not found")
                return CapabilityOutput(data={"config": row.get("cfg")})
            cur.execute("SELECT gid,parent_gid,node_type,sort_order,title FROM workmanship_bop_bop_entries WHERE version_gid=%s AND is_deleted=FALSE ORDER BY sort_order LIMIT 1000", (gid,))
            entries = [dict(row) for row in cur.fetchall()]
            if operation == "bop_tree":
                entry_map = {row["gid"]: row for row in entries}; children: dict[Any, list[Any]] = {}; roots = []
                for row in entries:
                    parent = row.get("parent_gid")
                    if parent and parent in entry_map: children.setdefault(parent, []).append(row["gid"])
                    else: roots.append(row["gid"])
                def build_node(node_gid: Any) -> dict[str, Any]:
                    row = entry_map[node_gid]; kids = sorted(children.get(node_gid, []), key=lambda child: entry_map[child].get("sort_order") or 0)
                    return {"name": row.get("title") or row.get("node_type"), "path": node_gid, "gid": node_gid, "node_type": row.get("node_type"), "sort_order": row.get("sort_order"), "is_leaf": not kids, "children": [build_node(child) for child in kids]}
                return CapabilityOutput(data={"tree": [build_node(root) for root in roots]})
            cur.execute("SELECT l.entry_gid,p.gid AS part_gid,p.part_no,p.title AS part_name,p.bom_row,p.vpps FROM workmanship_bop_bop_entry_links l JOIN workmanship_bop_pbom p ON p.gid=l.entity_gid JOIN workmanship_bop_bop_entries e ON e.gid=l.entry_gid WHERE e.version_gid=%s AND l.link_type='pbom_part' LIMIT 1000", (gid,))
            links = [dict(row) for row in cur.fetchall()]
    children_map: dict[Any, list[Any]] = {}; entry_parts: dict[Any, list[dict[str, Any]]] = {}
    entry_map = {row["gid"]: row for row in entries}
    for row in entries:
        if row.get("parent_gid"): children_map.setdefault(row["parent_gid"], []).append(row["gid"])
    for link in links: entry_parts.setdefault(link["entry_gid"], []).append(link)
    def descendants(node_gid: Any) -> list[Any]:
        result: list[Any] = []
        for child in children_map.get(node_gid, []): result.append(child); result.extend(descendants(child))
        return result
    stations = []
    for row in entries:
        if row.get("node_type") != "station_process": continue
        parts = []; seen = set()
        for child in [row["gid"], *descendants(row["gid"])]:
            for part in entry_parts.get(child, []):
                if part["part_gid"] not in seen: seen.add(part["part_gid"]); parts.append(dict(part))
        stations.append({"gid": row["gid"], "name": row.get("title"), "sort_order": row.get("sort_order") or 0, "parts": parts})
    stations.sort(key=lambda item: item["sort_order"])
    return CapabilityOutput(data={"stations": stations})


def register_bop_version_legacy_read_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.bop.version.legacy_read", owner="craft", description="Read bounded legacy BOP version layout, tree and station-part projections.", use_when="A governed consumer still requires one of the legacy BOP version read projections.", do_not_use_when="The consumer needs version CRUD or a revision-pinned navigation capability.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation", "version_gid"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "version_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "additionalProperties": True}, tags=("craft", "bop", "version", "read")), read_bop_version_legacy)
