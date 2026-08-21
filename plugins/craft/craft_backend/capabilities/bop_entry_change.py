"""Governed update and soft-delete of BOP main-tree entries."""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec

from ..data.connection import get_craft_conn
from ..routers._bop._constants import _AI00_LEVEL, _LINK_TARGET_TABLES
from ..routers._bop._helpers import _check_line_editable, _log_entry_op, _sync_child_vpps


OPERATIONS = ("update", "delete")
_UPDATE_FIELDS = frozenset({"parent_gid", "node_type", "sort_order", "title", "vpps", "vpps_desc", "parent_bop_title", "process_flow_pic", "cad_sim_pics", "meta"})
_OWNED_ENTITY_TYPES = frozenset({"bop_line", "bop_station", "bop_process", "bop_steps", "bop_operator"})
_ENTITY_TITLE_SYNC = {
    "bop_line": ("workmanship_bop_bop_line", "title"),
    "bop_station": ("workmanship_bop_bop_station", "title"),
    "bop_process": ("workmanship_bop_bop_process", "name"),
    "bop_steps": ("workmanship_bop_bop_steps", "title"),
    "bop_operator": ("workmanship_bop_bop_operator", "title"),
}


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _user(context: CapabilityContext) -> dict[str, Any]:
    roles = set(context.active_roles or ())
    org_role = next((role for role in ("super_admin", "team_admin", "project_admin", "member") if role in roles), None)
    return {"gid": context.user_gid, "name": context.user_gid, "org_role": org_role or "external"}


def _ensure_editable(cur: Any, version_gid: str, entry_gid: str, context: CapabilityContext) -> None:
    cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
    version = cur.fetchone()
    if not version:
        raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
    status = version.get("status") if isinstance(version, dict) else dict(version)["status"]
    if status != "active":
        raise CapabilityBusinessError("invalid_state", f"version {version_gid} is not editable (current: {status})")
    try:
        _check_line_editable(cur, version_gid, entry_gid, _user(context))
    except HTTPException as exc:
        raise CapabilityBusinessError("permission_denied", str(exc.detail)) from exc


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def apply_bop_entry_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    entry_gid = _required(payload, "entry_gid")
    if operation == "update":
        updates = payload.get("updates")
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty object")
        unknown = set(updates) - _UPDATE_FIELDS
        if unknown:
            raise ValueError(f"unsupported update fields: {', '.join(sorted(unknown))}")

    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT e.gid,e.version_gid,e.parent_gid,e.node_type,e.title,e.vpps,e.vpps_desc,e.parent_bop_title,e.meta "
            "FROM workmanship_bop_bop_entries e WHERE e.gid=%s AND e.is_deleted=FALSE",
            (entry_gid,),
        )
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
        entry = dict(row)
        version_gid = str(entry["version_gid"])
        _ensure_editable(cur, version_gid, entry_gid, context)

        if operation == "update":
            updates = dict(updates)
            sets: list[str] = []
            values: list[Any] = []
            for name in ("parent_gid", "node_type", "sort_order", "title", "vpps", "vpps_desc", "parent_bop_title"):
                if name in updates:
                    sets.append(f"{name}=%s")
                    values.append(updates[name])
            if "node_type" in updates:
                sets.append("ai00_level=%s")
                values.append(_AI00_LEVEL.get(updates["node_type"]))
            if "process_flow_pic" in updates:
                sets.append("process_flow_pic=%s")
                values.append(_json(updates["process_flow_pic"]))
            if "cad_sim_pics" in updates:
                sets.append("meta=JSON_SET(IFNULL(meta,'{}'),'$.cad_sim_pics',CAST(%s AS JSON))")
                values.append(_json(updates["cad_sim_pics"]))
            elif "meta" in updates:
                sets.append("meta=CAST(%s AS JSON)")
                values.append(_json(updates["meta"]))
            if not sets:
                raise ValueError("updates contain no supported fields")
            sets.append("updated_at=NOW()")
            cur.execute(f"UPDATE workmanship_bop_bop_entries SET {', '.join(sets)} WHERE gid=%s AND is_deleted=FALSE", [*values, entry_gid])
            if cur.rowcount == 0:
                raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
            if "title" in updates:
                cur.execute("SELECT entity_gid,link_type FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND is_primary=TRUE LIMIT 1", (entry_gid,))
                link = cur.fetchone()
                if link:
                    link = dict(link)
                    sync = _ENTITY_TITLE_SYNC.get(link.get("link_type"))
                    if sync:
                        cur.execute(f"UPDATE {sync[0]} SET {sync[1]}=%s WHERE gid=%s", (updates["title"], link["entity_gid"]))
            if "parent_gid" in updates and updates["parent_gid"] and updates["parent_gid"] != entry.get("parent_gid"):
                _sync_child_vpps(cur, updates["parent_gid"], version_gid)
            _log_entry_op(cur, version_gid=version_gid, entry_gid=entry_gid, entry_title=str(updates.get("title") or entry.get("title") or ""), op_type="update_entry",
                          old_state=entry, new_state=updates, user_gid=context.user_gid, user_name=context.user_gid)
            conn.commit()
            cur.execute("SELECT * FROM workmanship_bop_bop_entries WHERE gid=%s", (entry_gid,))
            return {"data": dict(cur.fetchone() or {}), "version_gid": version_gid}

        cur.execute("SELECT parent_gid,title,node_type,vpps FROM workmanship_bop_bop_entries WHERE gid=%s", (entry_gid,))
        current = dict(cur.fetchone() or {})
        cur.execute("UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE,deleted_at=NOW() WHERE gid=%s AND is_deleted=FALSE", (entry_gid,))
        if cur.rowcount == 0:
            raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
        cur.execute("SELECT entity_gid,link_type,is_primary FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND deleted_at IS NULL", (entry_gid,))
        links = [dict(item) for item in cur.fetchall()]
        for link in links:
            if link.get("link_type") not in _OWNED_ENTITY_TYPES:
                continue
            table_info = _LINK_TARGET_TABLES.get(link["link_type"])
            if table_info:
                cur.execute(f"UPDATE {table_info[0]} SET deleted_at=NOW() WHERE {table_info[1]}=%s AND deleted_at IS NULL", (link["entity_gid"],))
        cur.execute("UPDATE workmanship_bop_bop_entry_links SET deleted_at=NOW() WHERE entry_gid=%s AND deleted_at IS NULL", (entry_gid,))
        if current.get("parent_gid"):
            _sync_child_vpps(cur, current["parent_gid"], version_gid)
        _log_entry_op(cur, version_gid=version_gid, entry_gid=entry_gid, entry_title=current.get("title") or "", op_type="delete_entry",
                      old_state={**current, "links": links}, new_state=None, user_gid=context.user_gid, user_name=context.user_gid)
        conn.commit()
    return {"data": {"deleted": True, "gid": entry_gid}, "version_gid": version_gid}


def register_bop_entry_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.entry.change.apply", owner="craft",
        description="Update or soft-delete an active BOP main-tree entry with linked-entity and audit semantics.",
        use_when="A governed Craft consumer edits fields on, or removes, one active BOP entry.",
        do_not_use_when="The request creates/copies/imports entries, changes links only, or operates on staging.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "entry_gid"], "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": True},
        tags=("craft", "bop", "entry", "write"),
    ), apply_bop_entry_change)


__all__ = ["OPERATIONS", "apply_bop_entry_change", "register_bop_entry_change_capability"]
