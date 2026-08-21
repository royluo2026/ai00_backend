"""Bounded read projection for BOP station auto-link previews."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilitySpec,
)

from ..data.connection import get_craft_conn


OPERATIONS = ("preview",)
_MAX_ITEMS = 500


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _bounded_result(lines: list[dict[str, Any]], data: list[dict[str, Any]]) -> None:
    if len(lines) > _MAX_ITEMS or len(data) > _MAX_ITEMS:
        raise CapabilityBusinessError(
            "invalid_input",
            "station auto-link preview exceeds the bounded response limit",
            details={"limit": _MAX_ITEMS, "line_count": len(lines), "item_count": len(data)},
        )


def preview_station_autolink(
    payload: dict[str, Any], _context: CapabilityContext
) -> CapabilityOutput:
    if str(payload.get("operation") or "preview") not in OPERATIONS:
        raise ValueError("unsupported station auto-link preview operation")
    bop_gid = _required_text(payload, "bop_gid")
    requested_pbom_gid = str(payload.get("pbom_version_gid") or "").strip() or None

    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT project_gid, pbom_version_gid "
                "FROM workmanship_bop_bop_versions WHERE gid=%s",
                (bop_gid,),
            )
            bop_ver = cur.fetchone()
            if not bop_ver:
                raise CapabilityBusinessError(
                    "resource_not_found", f"BOP version {bop_gid} does not exist"
                )
            pbom_gid = requested_pbom_gid or bop_ver["pbom_version_gid"]
            project_gid = bop_ver["project_gid"]

            if not pbom_gid:
                pbom_versions: list[dict[str, Any]] = []
                if project_gid:
                    cur.execute(
                        "SELECT gid, COALESCE(NULLIF(name,''), "
                        "NULLIF(version_tag,''), gid) AS display_name, status, created_at "
                        "FROM workmanship_bop_pbom_versions "
                        "WHERE project_gid=%s AND status='ready' ORDER BY created_at DESC",
                        (project_gid,),
                    )
                    pbom_versions = [dict(row) for row in cur.fetchall()]
                _bounded_result([], pbom_versions)
                return CapabilityOutput(
                    data={
                        "need_select": True,
                        "pbom_version": {"gid": "", "name": "", "project_name": ""},
                        "pbom_versions": pbom_versions,
                        "lines": [],
                        "data": [],
                    }
                )

            cur.execute(
                "SELECT COALESCE(NULLIF(name,''), NULLIF(version_tag,''), gid) AS display_name "
                "FROM workmanship_bop_pbom_versions WHERE gid=%s",
                (pbom_gid,),
            )
            pbom_row = cur.fetchone()
            pbom_name = pbom_row["display_name"] if pbom_row else pbom_gid

            cur.execute(
                "SELECT gbop_process_entry_gid, gbop_op_entry_gid, pbom_entry_gid, "
                "COALESCE(is_part_feed, FALSE) AS is_part_feed "
                "FROM workmanship_bop_gbop_nav_bindings "
                "WHERE pbom_version_gid=%s AND confirmed=TRUE",
                (pbom_gid,),
            )
            bindings = [dict(row) for row in cur.fetchall()]
            if not bindings:
                return CapabilityOutput(
                    data={
                        "pbom_version": {
                            "gid": pbom_gid,
                            "name": pbom_name,
                            "project_name": "",
                        },
                        "lines": [],
                        "data": [],
                    }
                )

            proc_gids = list({row["gbop_process_entry_gid"] for row in bindings if row["gbop_process_entry_gid"]})
            op_gids = list({row["gbop_op_entry_gid"] for row in bindings if row["gbop_op_entry_gid"]})
            part_gids = list({row["pbom_entry_gid"] for row in bindings if row["pbom_entry_gid"]})

            entry_map: dict[str, dict[str, Any]] = {}
            all_entry_gids = proc_gids + op_gids
            if all_entry_gids:
                placeholders = ",".join(["%s"] * len(all_entry_gids))
                cur.execute(
                    "SELECT gid, vpps, vpps_desc, node_type, seq_no, parent_gid "
                    "FROM workmanship_tpl_gbop_entries "
                    f"WHERE gid IN ({placeholders})",
                    all_entry_gids,
                )
                entry_map = {row["gid"]: dict(row) for row in cur.fetchall()}

            part_info_map: dict[str, dict[str, Any]] = {}
            if part_gids:
                placeholders = ",".join(["%s"] * len(part_gids))
                cur.execute(
                    "SELECT gid, vpps, title, part_no FROM workmanship_bop_pbom "
                    f"WHERE gid IN ({placeholders})",
                    part_gids,
                )
                part_info_map = {row["gid"]: dict(row) for row in cur.fetchall()}

            cur.execute(
                "SELECT DISTINCT vpps FROM workmanship_bop_bop_entries "
                "WHERE version_gid=%s AND node_type='process' "
                "AND is_deleted=FALSE AND vpps IS NOT NULL",
                (bop_gid,),
            )
            existing_proc_vpps = {row["vpps"] for row in cur.fetchall()}

            cur.execute(
                "SELECT gid, parent_gid, child_vpps FROM workmanship_bop_bop_entries "
                "WHERE version_gid=%s AND node_type='station_process' AND is_deleted=FALSE",
                (bop_gid,),
            )
            proc_vpps_to_line_gids: dict[str, set[str | None]] = {}
            raw_line_gids: set[str] = set()
            for station in cur.fetchall():
                child_vpps = station["child_vpps"] or []
                if isinstance(child_vpps, str):
                    child_vpps = json.loads(child_vpps)
                line_gid = station["parent_gid"]
                for child in child_vpps:
                    vpps = child.get("vpps", "") if isinstance(child, dict) else ""
                    if vpps:
                        proc_vpps_to_line_gids.setdefault(vpps, set()).add(line_gid)
                        if line_gid:
                            raw_line_gids.add(line_gid)

            line_map: dict[str, dict[str, Any]] = {}
            if raw_line_gids:
                line_list = list(raw_line_gids)
                placeholders = ",".join(["%s"] * len(line_list))
                cur.execute(
                    "SELECT gid, title, vpps, sort_order "
                    "FROM workmanship_bop_bop_entries "
                    f"WHERE gid IN ({placeholders}) AND is_deleted=FALSE",
                    line_list,
                )
                line_map = {row["gid"]: dict(row) for row in cur.fetchall()}

            line_proc_count: dict[str, set[str]] = {}
            for vpps, line_gids in proc_vpps_to_line_gids.items():
                for line_gid in line_gids:
                    if line_gid:
                        line_proc_count.setdefault(line_gid, set()).add(vpps)
            lines = sorted(
                [
                    {
                        "gid": line_gid,
                        "title": line_map.get(line_gid, {}).get("title") or line_gid,
                        "vpps": line_map.get(line_gid, {}).get("vpps") or "",
                        "process_count": len(processes),
                    }
                    for line_gid, processes in line_proc_count.items()
                ],
                key=lambda item: line_map.get(item["gid"], {}).get("sort_order") or 0,
            )

    op_by_proc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    parts_by_op: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for binding in bindings:
        proc_gid = binding["gbop_process_entry_gid"]
        op_gid = binding["gbop_op_entry_gid"]
        part_gid = binding["pbom_entry_gid"]
        is_part_feed = bool(binding.get("is_part_feed", False))
        if op_gid and proc_gid and op_gid not in [item["gid"] for item in op_by_proc[proc_gid]]:
            operation = entry_map.get(op_gid, {})
            op_by_proc[proc_gid].append(
                {
                    "gid": op_gid,
                    "vpps": operation.get("vpps", ""),
                    "title": operation.get("vpps_desc") or operation.get("vpps") or op_gid,
                    "seq_no": operation.get("seq_no") or 0,
                }
            )
        if op_gid and part_gid:
            part = part_info_map.get(part_gid, {})
            existing = parts_by_op[op_gid].get(part_gid)
            if existing:
                existing["is_part_feed"] = existing["is_part_feed"] or is_part_feed
            else:
                parts_by_op[op_gid][part_gid] = {
                    "gid": part_gid,
                    "vpps": part.get("vpps", ""),
                    "title": part.get("title") or part.get("part_no") or part_gid,
                    "is_part_feed": is_part_feed,
                }

    data: list[dict[str, Any]] = []
    for proc_gid in proc_gids:
        process = entry_map.get(proc_gid, {})
        proc_vpps = process.get("vpps", "")
        linked = proc_vpps in existing_proc_vpps if proc_vpps else False
        data.append(
            {
                "gid": proc_gid,
                "vpps": proc_vpps,
                "title": process.get("vpps_desc") or proc_vpps or proc_gid,
                "type": "process",
                "parent_gid": None,
                "linked": linked,
                "seq_no": process.get("seq_no") or 0,
                "line_gids": list(proc_vpps_to_line_gids.get(proc_vpps, set()) - {None}),
            }
        )
        for operation in sorted(op_by_proc.get(proc_gid, []), key=lambda item: item["seq_no"]):
            data.append(
                {
                    "gid": operation["gid"],
                    "vpps": operation["vpps"],
                    "title": operation["title"],
                    "type": "operation",
                    "parent_gid": proc_gid,
                    "linked": linked,
                    "seq_no": operation["seq_no"],
                }
            )
            for part in parts_by_op.get(operation["gid"], {}).values():
                data.append(
                    {
                        "gid": part["gid"],
                        "vpps": part["vpps"],
                        "title": part["title"],
                        "type": "part",
                        "parent_gid": operation["gid"],
                        "linked": linked,
                        "is_part_feed": part["is_part_feed"],
                    }
                )

    _bounded_result(lines, data)
    return CapabilityOutput(
        data={
            "pbom_version": {"gid": pbom_gid, "name": pbom_name, "project_name": ""},
            "lines": lines,
            "data": data,
        }
    )


def register_station_autolink_preview_capability(registry: Any) -> None:
    registry.register(
        CapabilitySpec(
            id="craft.gbop.station_autolink.preview",
            owner="craft",
            description="Preview bounded BOP station auto-link candidates without mutating bindings.",
            use_when="A governed Craft consumer needs to inspect station/process auto-link candidates.",
            do_not_use_when="The consumer confirms, executes, or undoes station auto-link bindings.",
            risk="read",
            permissions=("craft.read",),
            input_schema={
                "type": "object",
                "required": ["operation", "bop_gid"],
                "properties": {
                    "operation": {"type": "string", "enum": list(OPERATIONS)},
                    "bop_gid": {"type": "string"},
                    "pbom_version_gid": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["pbom_version", "lines", "data"],
                "properties": {
                    "pbom_version": {"type": "object", "additionalProperties": True},
                    "lines": {"type": "array", "maxItems": _MAX_ITEMS, "items": {"type": "object", "additionalProperties": True}},
                    "data": {"type": "array", "maxItems": _MAX_ITEMS, "items": {"type": "object", "additionalProperties": True}},
                    "need_select": {"type": "boolean"},
                    "pbom_versions": {"type": "array", "maxItems": _MAX_ITEMS, "items": {"type": "object", "additionalProperties": True}},
                },
                "additionalProperties": False,
            },
            tags=("craft", "gbop", "station", "autolink", "preview", "read"),
        ),
        preview_station_autolink,
    )


__all__ = ["OPERATIONS", "preview_station_autolink", "register_station_autolink_preview_capability"]
