"""Bounded read projections for legacy GBOP matching routes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn

OPERATIONS = ("match_preview", "list_pbom_versions")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def read_bop_gbop_legacy(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported GBOP legacy read operation")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "list_pbom_versions":
                project_gid = str(payload.get("project_gid") or "")
                if not project_gid:
                    raise ValueError("project_gid is required")
                cur.execute("SELECT gid,COALESCE(NULLIF(name,''),NULLIF(version_tag,''),gid) AS title,status,created_at FROM workmanship_bop_pbom_versions WHERE project_gid=%s AND status='ready' ORDER BY created_at DESC", (project_gid,))
                return CapabilityOutput(data={"data": [{key: _jsonable(value) for key, value in dict(row).items()} for row in cur.fetchall()]})

            pbom_gid = str(payload.get("pbom_gid") or "")
            if not pbom_gid:
                raise ValueError("pbom_gid is required")
            cur.execute("SELECT gid FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_gid,))
            if not cur.fetchone():
                raise LookupError("pbom_version_not_found")
            cur.execute("SELECT p.gid,p.vpps,p.title,p.part_no,p.bom_row,p.parent_gid,p.level,p.parent_bom_row,p.parent_vpps FROM workmanship_bop_pbom p WHERE p.snapshot_gid=%s AND p.is_deleted=FALSE ORDER BY p.level,p.bom_row,p.vpps", (pbom_gid,))
            parts = [{key: _jsonable(value) for key, value in dict(row).items()} for row in cur.fetchall()]
            if not parts:
                return CapabilityOutput(data={"data": [], "pbom_version_gid": pbom_gid})
            by_bom = {p["bom_row"]: p["gid"] for p in parts if p.get("bom_row")}
            by_vpps = {p["vpps"]: p["gid"] for p in parts if p.get("vpps")}
            for part in parts:
                if not part.get("parent_gid"):
                    part["parent_gid"] = by_bom.get(part.get("parent_bom_row")) or by_vpps.get(part.get("parent_vpps"))
            cur.execute("SELECT e.gid AS entry_gid,e.vpps,e.node_type,e.title,e.version_gid,COALESCE((SELECT l.is_primary FROM workmanship_bop_bop_entry_links l WHERE l.entry_gid=e.gid AND l.link_type='pbom_part' AND l.is_deleted=FALSE LIMIT 1),FALSE) AS is_primary_feed FROM workmanship_bop_bop_entries e JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid WHERE v.version_type='template' AND v.is_deleted=FALSE AND e.is_deleted=FALSE AND e.vpps IS NOT NULL")
            entries = [{key: _jsonable(value) for key, value in dict(row).items()} for row in cur.fetchall()]
            by_entry: dict[str, list[dict[str, Any]]] = {}
            for entry in entries:
                by_entry.setdefault(entry["vpps"], []).append(entry)
            cur.execute("SELECT pbom_entry_gid,match_status FROM workmanship_bop_gbop_match_staging WHERE pbom_version_gid=%s", (pbom_gid,))
            staged = {row["pbom_entry_gid"]: dict(row) for row in cur.fetchall()}
            result = []
            for part in parts:
                matches = by_entry.get(part.get("vpps"), []) if part.get("vpps") else []
                status = "unmatched" if not matches else "matched_1" if len(matches) == 1 else "matched_n"
                staging = staged.get(part["gid"])
                result.append({"pbom_entry_gid": part["gid"], "vpps": part.get("vpps"), "part_title": part.get("title"), "part_number": part.get("part_no"), "parent_gid": part.get("parent_gid"), "level": part.get("level"), "match_status": status, "confirmed_status": staging.get("match_status") if staging else None, "gbop_matches": [{"entry_gid": e["entry_gid"], "node_type": e["node_type"], "title": e["title"], "version_gid": e["version_gid"], "is_primary_feed": e.get("is_primary_feed", False)} for e in matches]})
            return CapabilityOutput(data={"data": result, "pbom_version_gid": pbom_gid})


def register_bop_gbop_legacy_read_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.gbop.legacy_read", owner="craft",
        description="Read legacy GBOP matching previews and ready PBOM version choices.",
        use_when="A governed Craft consumer needs the legacy GBOP match preview or PBOM version selector.",
        do_not_use_when="The request confirms matches, writes links, or performs auto-link mutations.",
        risk="read", permissions=("craft.read",),
        input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "pbom_gid": {"type": "string"}, "project_gid": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": ["array", "object"], "additionalProperties": True}, "pbom_version_gid": {"type": "string"}}, "additionalProperties": False},
        tags=("craft", "bop", "gbop", "legacy", "read"),
    ), read_bop_gbop_legacy)
