"""Read the bounded GBOP process/operation/part hierarchy projection."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn


def read_gbop_process_hierarchy(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    pbom_gid = str(payload.get("pbom_version_gid") or "")
    if not pbom_gid:
        raise ValueError("pbom_version_gid is required")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT e.gid, e.vpps, e.vpps_desc, e.node_type, e.seq_no, e.parent_gid, e.part_feed "
                "FROM workmanship_tpl_gbop_entries e "
                "JOIN workmanship_tpl_gbop_versions v ON v.gid = e.version_gid "
                "WHERE e.node_type IN ('process', 'operation') AND v.archived_at IS NULL "
                "ORDER BY e.seq_no LIMIT 500",
            )
            all_entries = [dict(row) for row in cur.fetchall()]
            if not all_entries:
                return CapabilityOutput(data={"data": []})
            cur.execute(
                "SELECT gbop_op_entry_gid, pbom_entry_gid, confirmed "
                "FROM workmanship_bop_gbop_nav_bindings WHERE pbom_version_gid=%s LIMIT 500",
                (pbom_gid,),
            )
            bindings = [dict(row) for row in cur.fetchall()]
            part_gids = list({row["pbom_entry_gid"] for row in bindings if row.get("pbom_entry_gid")})
            part_map: dict[Any, dict[str, Any]] = {}
            if part_gids:
                placeholders = ",".join(["%s"] * len(part_gids))
                cur.execute(
                    f"SELECT gid, vpps, title, part_no FROM workmanship_bop_pbom WHERE gid IN ({placeholders}) LIMIT 500",
                    part_gids,
                )
                part_map = {row["gid"]: dict(row) for row in cur.fetchall()}

    entry_map = {row["gid"]: row for row in all_entries}
    op_parts: dict[Any, list[dict[str, Any]]] = {}
    for binding in bindings:
        part = part_map.get(binding.get("pbom_entry_gid"))
        if part:
            op_parts.setdefault(binding["gbop_op_entry_gid"], []).append({
                "pbom_entry_gid": binding["pbom_entry_gid"],
                "vpps": part.get("vpps", ""),
                "title": part.get("title", ""),
                "part_no": part.get("part_no", ""),
                "confirmed": binding.get("confirmed", False),
            })
    proc_ops: dict[Any, list[dict[str, Any]]] = {}
    for entry in all_entries:
        if entry.get("node_type") == "operation":
            parent = entry.get("parent_gid")
            if parent in entry_map and entry_map[parent].get("node_type") == "process":
                proc_ops.setdefault(parent, []).append(entry)
    result = []
    for entry in all_entries:
        if entry.get("node_type") != "process":
            continue
        operations = []
        for operation in sorted(proc_ops.get(entry["gid"], []), key=lambda row: row.get("seq_no") or 0):
            operations.append({
                "entry_gid": operation["gid"],
                "vpps": operation.get("vpps", ""),
                "title": operation.get("vpps_desc") or operation.get("vpps") or operation["gid"],
                "seq_no": operation.get("seq_no") or 0,
                "part_feed": operation.get("part_feed", False),
                "parts": op_parts.get(operation["gid"], []),
            })
        result.append({
            "process_entry_gid": entry["gid"],
            "vpps": entry.get("vpps", ""),
            "title": entry.get("vpps_desc") or entry.get("vpps") or "（无工序）",
            "seq_no": entry.get("seq_no") or 0,
            "operations": operations,
            "op_count": len(operations),
            "part_count": sum(len(item["parts"]) for item in operations),
        })
    result.sort(key=lambda row: row["seq_no"])
    return CapabilityOutput(data={"data": result})


def register_gbop_process_hierarchy_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.gbop.process_hierarchy.read", owner="craft",
        description="Read the bounded GBOP process-operation-part hierarchy for a PBOM version.",
        use_when="A governed consumer needs the GBOP process hierarchy and confirmed PBOM part bindings.",
        do_not_use_when="The request mutates GBOP/PBOM bindings or creates BOP entries.", risk="read",
        permissions=("craft.read",),
        input_schema={"type": "object", "required": ["pbom_version_gid"], "properties": {"pbom_version_gid": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False},
        tags=("craft", "gbop", "hierarchy", "read"),
    ), read_gbop_process_hierarchy)
