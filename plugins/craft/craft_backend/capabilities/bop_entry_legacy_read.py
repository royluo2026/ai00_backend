"""Bounded read projections for legacy BOP entry routes."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec
from backend.platform_sdk.identity import resolve_identity_labels

from ..data.connection import get_craft_conn
from ..routers._bop._constants import _GID_RESOLVE_MAP, _LINK_TARGET_TABLES, _PART_NODE_TYPES, _PROCESS_ENTITY_MAP

OPERATIONS = (
    "auto_link_preview", "entry_links", "link_summary", "entity_detail", "resolve_gids",
    "pbom_search", "pbom_snapshots", "project_bop_lines", "line_operations", "version_history", "entry_history",
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return value


def _rows(cursor) -> list[dict[str, Any]]:
    return [{key: _jsonable(value) for key, value in dict(row).items()} for row in cursor.fetchall()]


def _parse_json(value: Any, default: Any = None) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value if value is not None else default


def read_bop_entry_legacy(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported BOP entry read operation")
    limit = payload.get("limit", 100)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "auto_link_preview":
                version_gid = str(payload.get("version_gid") or "")
                if not version_gid:
                    raise ValueError("version_gid is required")
                cur.execute("SELECT 1 FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
                if not cur.fetchone():
                    raise LookupError("version_not_found")
                types = list(_PROCESS_ENTITY_MAP) + list(_PART_NODE_TYPES)
                placeholders = ",".join(["%s"] * len(types))
                cur.execute(
                    "SELECT e.gid,e.node_type,e.title,e.vpps,e.vpps_desc,e.sort_order "
                    "FROM workmanship_bop_bop_entries e WHERE e.version_gid=%s AND e.is_deleted=FALSE "
                    f"AND e.node_type IN ({placeholders}) ORDER BY e.sort_order LIMIT %s",
                    [version_gid, *types, limit],
                )
                entries = _rows(cur)
                cur.execute("SELECT entry_gid FROM workmanship_bop_bop_entry_links WHERE entry_gid IN (SELECT gid FROM workmanship_bop_bop_entries WHERE version_gid=%s) AND is_primary=TRUE", (version_gid,))
                linked = {row["entry_gid"] for row in cur.fetchall()}
                items = []
                for entry in entries:
                    node_type = entry["node_type"]
                    item = {"entry_gid": entry["gid"], "node_type": node_type, "title": entry.get("title") or "", "vpps": entry.get("vpps") or "", "sort_order": entry.get("sort_order"), "status": "skip" if entry["gid"] in linked else "pending", "message": "已有关联" if entry["gid"] in linked else ""}
                    if item["status"] != "skip":
                        if node_type in _PROCESS_ENTITY_MAP:
                            item.update(action="建 stub 实体 → link", step="A")
                        elif node_type in _PART_NODE_TYPES:
                            if not entry.get("bom_row_id"):
                                item.update(status="warn", message="bom_row_id 为空，无法匹配")
                            else:
                                item.update(action="按 bom_row_id 匹配零件", step="B")
                    items.append(item)
                data = {"version_gid": version_gid, "total": len(items), "pending": sum(i["status"] == "pending" for i in items), "skip": sum(i["status"] == "skip" for i in items), "warn": sum(i["status"] == "warn" for i in items), "items": items}
                return CapabilityOutput(data={"data": data})

            if operation == "entry_links":
                entry_gid = str(payload.get("entry_gid") or "")
                if not entry_gid:
                    raise ValueError("entry_gid is required")
                recursive = bool(payload.get("recursive", False))
                if recursive:
                    cur.execute("""WITH RECURSIVE descendants AS (SELECT gid,title FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted=FALSE UNION ALL SELECT e.gid,e.title FROM workmanship_bop_bop_entries e JOIN descendants d ON e.parent_gid=d.gid WHERE e.is_deleted=FALSE) SELECT l.gid,l.entry_gid,l.version_gid,l.link_type,l.entity_gid,l.is_primary,l.is_inherited,l.snapshot_data,l.created_at,l.created_by,d.gid AS source_entry_gid,d.title AS source_entry_title FROM workmanship_bop_bop_entry_links l JOIN descendants d ON l.entry_gid=d.gid WHERE l.deleted_at IS NULL ORDER BY d.gid,l.link_type,l.created_at LIMIT %s""", (entry_gid, limit))
                else:
                    cur.execute("SELECT gid,entry_gid,version_gid,link_type,entity_gid,is_primary,is_inherited,snapshot_data,created_at,created_by FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND deleted_at IS NULL ORDER BY created_at LIMIT %s", (entry_gid, limit))
                rows = _rows(cur)
                for row in rows:
                    row.setdefault("source_entry_gid", row.get("entry_gid"))
                    row.setdefault("source_entry_title", None)
                pbom_gids = [row["entity_gid"] for row in rows if row.get("link_type") == "pbom_part"]
                if pbom_gids:
                    placeholders = ",".join(["%s"] * len(pbom_gids))
                    cur.execute(f"SELECT gid,part_no,title,vpps FROM workmanship_bop_pbom WHERE gid IN ({placeholders})", pbom_gids)
                    parts = {row["gid"]: dict(row) for row in cur.fetchall()}
                    for row in rows:
                        if row.get("link_type") == "pbom_part":
                            part = parts.get(row["entity_gid"], {})
                            row.update(entity_part_no=part.get("part_no") or "", entity_title=part.get("title") or "", entity_vpps=part.get("vpps") or "")
                return CapabilityOutput(data={"data": rows})

            if operation == "link_summary":
                version_gid = str(payload.get("version_gid") or "")
                if not version_gid:
                    raise ValueError("version_gid is required")
                link_type = payload.get("link_type")
                query = "SELECT l.gid,l.entry_gid,l.link_type,l.entity_gid,l.is_primary,l.snapshot_data FROM workmanship_bop_bop_entry_links l JOIN workmanship_bop_bop_entries e ON e.gid=l.entry_gid WHERE e.version_gid=%s AND e.is_deleted=FALSE"
                params: list[Any] = [version_gid]
                if link_type:
                    query += " AND l.link_type=%s"
                    params.append(link_type)
                cur.execute(query, params)
                links = _rows(cur)
                summary: dict[str, Any] = {}
                for link in links:
                    table_info = _LINK_TARGET_TABLES.get(link["link_type"])
                    valid = True
                    if table_info and table_info[0]:
                        table, gid_col, deleted_col = table_info
                        deleted = f" AND {deleted_col} IS NULL" if deleted_col else ""
                        cur.execute(f"SELECT {gid_col} FROM {table} WHERE {gid_col}=%s{deleted} LIMIT 1", (link["entity_gid"],))
                        valid = bool(cur.fetchone())
                    summary[link["entity_gid"]] = {"entry_gid": link["entry_gid"], "link_gid": link["gid"], "link_type": link["link_type"], "is_primary": link["is_primary"], "is_valid": valid, **({"snapshot_data": link["snapshot_data"]} if link.get("snapshot_data") else {})}
                return CapabilityOutput(data={"data": summary})

            if operation == "entity_detail":
                link_type, ref_gid = str(payload.get("link_type") or ""), str(payload.get("ref_gid") or "")
                table_info = _LINK_TARGET_TABLES.get(link_type)
                if not table_info or not table_info[0] or not ref_gid:
                    raise ValueError("link_type and ref_gid identify a readable entity")
                table, gid_col, deleted_col = table_info
                deleted = f" AND {deleted_col} IS NULL" if deleted_col else ""
                cur.execute(f"SELECT * FROM {table} WHERE {gid_col}=%s{deleted} LIMIT 1", (ref_gid,))
                row = cur.fetchone()
                if not row:
                    raise LookupError("entity_not_found")
                data = {key: _jsonable(value) for key, value in dict(row).items()}
                data.update(_link_type=link_type, _table=table)
                return CapabilityOutput(data={"data": data})

            if operation == "resolve_gids":
                gids = payload.get("gids")
                if not isinstance(gids, dict):
                    raise ValueError("gids must be an object")
                result = dict(resolve_identity_labels(gids))
                for field, gid in gids.items():
                    if not gid or field not in _GID_RESOLVE_MAP:
                        continue
                    table, name_col = _GID_RESOLVE_MAP[field]
                    try:
                        cur.execute(f"SELECT {name_col} FROM {table} WHERE gid=%s LIMIT 1", (gid,))
                        row = cur.fetchone()
                        if row:
                            result[field] = row[name_col]
                    except Exception:
                        continue
                return CapabilityOutput(data={"data": result})

            if operation == "pbom_search":
                q, vpps, snapshot_gid = payload.get("q"), payload.get("vpps"), payload.get("snapshot_gid")
                like = f"%{q}%" if q else None
                cur.execute("SELECT p.gid,p.part_no,p.title,p.quantity,p.unit,p.vpps,p.parent_gid,p.snapshot_gid,pv.version_tag FROM workmanship_bop_pbom p JOIN workmanship_bop_pbom_versions pv ON pv.gid=p.snapshot_gid WHERE (%s IS NULL OR p.part_no LIKE %s OR p.title LIKE %s) AND (%s IS NULL OR p.vpps=%s) AND (%s IS NULL OR p.snapshot_gid=%s) ORDER BY pv.version_tag,p.part_no LIMIT %s", (like, like, like, vpps, vpps, snapshot_gid, snapshot_gid, limit))
                rows = _rows(cur)
                return CapabilityOutput(data={"data": rows, "total": len(rows)})

            if operation == "pbom_snapshots":
                project_gid = payload.get("project_gid")
                cur.execute("SELECT pv.gid,pv.version_tag,pv.source_type,pv.status,pv.project_gid,pv.created_at,COUNT(p.gid) AS part_count FROM workmanship_bop_pbom_versions pv LEFT JOIN workmanship_bop_pbom p ON p.snapshot_gid=pv.gid WHERE (%s IS NULL OR pv.project_gid=%s) GROUP BY pv.gid,pv.version_tag,pv.source_type,pv.status,pv.project_gid,pv.created_at ORDER BY pv.created_at DESC LIMIT %s", (project_gid, project_gid, limit))
                rows = _rows(cur)
                return CapabilityOutput(data={"data": rows, "total": len(rows)})

            if operation == "project_bop_lines":
                project_gid = str(payload.get("project_gid") or "").strip()
                if not project_gid:
                    raise ValueError("project_gid is required")
                cur.execute("SELECT e.gid,e.title,e.sort_order FROM workmanship_bop_bop_entries e WHERE e.version_gid IN (SELECT gid FROM workmanship_bop_bop_versions WHERE project_gid=%s AND archived_at IS NULL) AND e.node_type='line_process' AND e.is_deleted=FALSE ORDER BY e.sort_order,e.title LIMIT %s", (project_gid, limit))
                grouped: dict[str, dict[str, Any]] = {}
                for row in cur.fetchall():
                    title = row["title"] or ""
                    grouped.setdefault(title, {"gid": row["gid"], "title": title or "（未命名线体）", "seq_no": row["sort_order"], "all_gids": []})["all_gids"].append(row["gid"])
                return CapabilityOutput(data={"data": list(grouped.values())})

            if operation == "line_operations":
                line_gid = str(payload.get("line_entry_gid") or "")
                if not line_gid:
                    raise ValueError("line_entry_gid is required")
                cur.execute("""WITH RECURSIVE desc_entries AS (SELECT gid,title,sort_order,node_type,parent_gid,process_flow_pic,meta FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted=FALSE UNION ALL SELECT b.gid,b.title,b.sort_order,b.node_type,b.parent_gid,b.process_flow_pic,b.meta FROM workmanship_bop_bop_entries b JOIN desc_entries d ON b.parent_gid=d.gid WHERE b.is_deleted=FALSE) SELECT gid AS bop_entry_gid,title,sort_order,parent_gid,COALESCE(process_flow_pic,'[]') AS process_flow_pic,IFNULL(JSON_EXTRACT(meta,'$.cad_sim_pics'),'[]') AS cad_sim_pics FROM desc_entries WHERE node_type='operation' ORDER BY sort_order DESC LIMIT %s""", (line_gid, limit))
                items = []
                for row in cur.fetchall():
                    item = dict(row)
                    item["process_flow_pic"] = _parse_json(item.get("process_flow_pic"), [])
                    item["cad_sim_pics"] = _parse_json(item.get("cad_sim_pics"), [])
                    items.append({key: _jsonable(value) for key, value in item.items()})
                return CapabilityOutput(data={"ok": True, "data": items})

            if operation == "version_history":
                version_gid = str(payload.get("version_gid") or "")
                if not version_gid:
                    raise ValueError("version_gid is required")
                cur.execute("SELECT gid,op_type,entity_gid,entity_title,old_state,new_state,performed_by,performed_by_name,performed_at,rolled_back FROM workmanship_bop_bop_line_operation_log WHERE version_gid=%s ORDER BY performed_at DESC LIMIT %s", (version_gid, limit))
                rows = _rows(cur)
                for row in rows:
                    for field in ("old_state", "new_state"):
                        row[field] = _parse_json(row.get(field))
                return CapabilityOutput(data={"data": rows})

            entry_gid = str(payload.get("entry_gid") or "")
            if not entry_gid:
                raise ValueError("entry_gid is required")
            cur.execute("SELECT gid,op_type,entity_title,old_state,new_state,performed_by,performed_by_name,performed_at,rolled_back FROM workmanship_bop_bop_line_operation_log WHERE entity_gid=%s ORDER BY performed_at DESC LIMIT %s", (entry_gid, min(limit, 50)))
            rows = _rows(cur)
            for row in rows:
                for field in ("old_state", "new_state"):
                    row[field] = _parse_json(row.get(field))
            return CapabilityOutput(data={"data": rows})


def register_bop_entry_legacy_read_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.entry.legacy_read", owner="craft",
        description="Read bounded legacy BOP entry links, PBOM projections, auto-link previews and history.",
        use_when="A governed Craft consumer still needs one of the supported legacy BOP entry read projections.",
        do_not_use_when="The request mutates entries, links, entities, imports data, or needs the canonical structure capability.",
        risk="read", permissions=("craft.read",),
        input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "version_gid": {"type": "string"}, "entry_gid": {"type": "string"}, "line_entry_gid": {"type": "string"}, "link_type": {"type": "string"}, "ref_gid": {"type": "string"}, "gids": {"type": "object", "additionalProperties": {"type": "string"}}, "recursive": {"type": "boolean"}, "q": {"type": ["string", "null"]}, "vpps": {"type": ["string", "null"]}, "snapshot_gid": {"type": ["string", "null"]}, "project_gid": {"type": ["string", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"ok": {"type": "boolean"}, "data": {"type": ["array", "object"], "additionalProperties": True}, "total": {"type": "integer"}}, "additionalProperties": False},
        tags=("craft", "bop", "entry", "legacy", "read"),
    ), read_bop_entry_legacy)
