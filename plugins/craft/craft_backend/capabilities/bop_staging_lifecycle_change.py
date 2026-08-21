"""Governed promotion and demotion between BOP staging and the main tree."""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn
from ..routers._bop._constants import _AI00_LEVEL
from ..routers._bop._helpers import _check_line_editable, _log_entry_op, _parent_level, _sync_child_vpps


OPERATIONS = ("demote", "promote")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _user(context: CapabilityContext) -> dict[str, Any]:
    roles = set(context.active_roles or ())
    org_role = next((role for role in ("super_admin", "team_admin", "project_admin", "member") if role in roles), None)
    return {"gid": context.user_gid, "name": context.user_gid, "org_role": org_role or "external"}


def _ensure_active(cur: Any, version_gid: str, context: CapabilityContext, entry_gid: str | None = None) -> None:
    cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
    row = cur.fetchone()
    if not row:
        raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
    status = row.get("status") if isinstance(row, dict) else dict(row)["status"]
    if status != "active":
        raise CapabilityBusinessError("invalid_state", f"version {version_gid} is not editable (current: {status})")
    if entry_gid:
        try:
            _check_line_editable(cur, version_gid, entry_gid, _user(context))
        except HTTPException as exc:
            raise CapabilityBusinessError("permission_denied", str(exc.detail)) from exc


def _descendants(cur: Any, root_gid: str, *, deleted: bool) -> list[str]:
    result: list[str] = []
    queue = [root_gid]
    flag = "TRUE" if deleted else "FALSE"
    while queue:
        parent = queue.pop()
        cur.execute(f"SELECT gid FROM workmanship_bop_bop_entries WHERE parent_gid=%s AND is_deleted={flag}", (parent,))
        children = [str(row["gid"] if isinstance(row, dict) else dict(row)["gid"]) for row in cur.fetchall()]
        result.extend(children)
        queue.extend(children)
    return result


def apply_bop_staging_lifecycle_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    if operation == "demote":
        entry_gid = _required(payload, "entry_gid")
    else:
        staging_gid = _required(payload, "staging_gid")
        parent_gid = str(payload.get("parent_gid") or "").strip() or None
        sort_order = payload.get("sort_order", 0)
        if isinstance(sort_order, bool) or not isinstance(sort_order, (int, float)):
            raise ValueError("sort_order must be a number")

    with get_craft_conn() as conn, conn.cursor() as cur:
        if operation == "demote":
            cur.execute(
                "SELECT gid, version_gid, parent_gid, node_type, title, vpps FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted=FALSE",
                (entry_gid,),
            )
            entry = cur.fetchone()
            if not entry:
                raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
            entry = dict(entry)
            _ensure_active(cur, entry["version_gid"], context, entry_gid)
            descendants = _descendants(cur, entry_gid, deleted=False)
            all_gids = [entry_gid, *descendants]
            placeholders = ",".join(["%s"] * len(all_gids))
            cur.execute(f"UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW() WHERE gid IN ({placeholders})", all_gids)
            if entry.get("parent_gid"):
                _sync_child_vpps(cur, entry["parent_gid"], entry["version_gid"])
            staging_gid = str(next_gid())
            cur.execute(
                "INSERT INTO workmanship_bop_bop_staging (gid,bop_version_gid,node_type,title,vpps,source_type,original_entry_gid,child_count,created_by) VALUES (%s,%s,%s,%s,%s,'bop_entry',%s,%s,%s)",
                (staging_gid, entry["version_gid"], entry["node_type"], entry["title"], entry["vpps"], entry_gid, len(descendants), context.user_gid),
            )
            _log_entry_op(cur, version_gid=entry["version_gid"], entry_gid=entry_gid, entry_title=entry.get("title") or "", op_type="demote_entry",
                          old_state={k: entry.get(k) for k in ("parent_gid", "node_type", "title", "vpps")},
                          new_state={"staging_gid": staging_gid, "child_count": len(descendants)}, user_gid=context.user_gid, user_name=context.user_gid)
            conn.commit()
            return {"data": {"staging_gid": staging_gid, "child_count": len(descendants)}}

        cur.execute("SELECT * FROM workmanship_bop_bop_staging WHERE gid=%s", (staging_gid,))
        staging = cur.fetchone()
        if not staging:
            raise CapabilityBusinessError("resource_not_found", f"BOP staging {staging_gid} does not exist")
        staging = dict(staging)
        version_gid = str(staging["bop_version_gid"])
        original_gid = staging.get("original_entry_gid")
        _ensure_active(cur, version_gid, context, str(parent_gid or original_gid or "") or None)
        result_gid: str
        if original_gid:
            restore_gids = [str(original_gid), *_descendants(cur, str(original_gid), deleted=True)]
            placeholders = ",".join(["%s"] * len(restore_gids))
            cur.execute(f"UPDATE workmanship_bop_bop_entries SET is_deleted=FALSE, deleted_at=NULL WHERE gid IN ({placeholders})", restore_gids)
            if parent_gid is not None:
                cur.execute("UPDATE workmanship_bop_bop_entries SET parent_gid=%s, sort_order=%s WHERE gid=%s", (parent_gid, sort_order, original_gid))
            result_gid = str(original_gid)
        elif staging.get("source_type") and staging.get("source_ref_gid"):
            if not parent_gid:
                raise ValueError("parent_gid is required for a linked staging item")
            meta = staging.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta) if meta else {}
                except (TypeError, ValueError):
                    meta = {}
            link_type = meta.get("link_type", staging["source_type"])
            cur.execute("INSERT INTO workmanship_bop_bop_entry_links (gid,entry_gid,version_gid,link_type,entity_gid,is_primary) VALUES (%s,%s,%s,%s,%s,%s)",
                        (str(next_gid()), parent_gid, version_gid, link_type, staging["source_ref_gid"], bool(meta.get("is_primary", False))))
            result_gid = parent_gid
        else:
            result_gid = str(next_gid())
            level = _parent_level(cur, parent_gid)
            cur.execute("INSERT INTO workmanship_bop_bop_entries (gid,version_gid,parent_gid,node_type,sort_order,level,ai00_level,title,vpps,meta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}')",
                        (result_gid, version_gid, parent_gid, staging["node_type"], sort_order, level, _AI00_LEVEL.get(staging["node_type"]), staging.get("title"), staging.get("vpps")))
        _log_entry_op(cur, version_gid=version_gid, entry_gid=result_gid, entry_title=staging.get("title") or "", op_type="promote_staging",
                      old_state={"staging_gid": staging_gid, "node_type": staging.get("node_type"), "title": staging.get("title"), "vpps": staging.get("vpps")},
                      new_state={"entry_gid": result_gid, "parent_gid": parent_gid, "sort_order": sort_order}, user_gid=context.user_gid, user_name=context.user_gid)
        cur.execute("DELETE FROM workmanship_bop_bop_staging WHERE gid=%s", (staging_gid,))
        conn.commit()
    return {"data": {"entry_gid": result_gid}}


def register_bop_staging_lifecycle_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.staging.lifecycle.change.apply", owner="craft",
        description="Promote a BOP staging item into the main tree or demote an entry into staging.",
        use_when="A governed Craft consumer moves a BOP entry between staging and the active tree.",
        do_not_use_when="The request edits staging metadata, copies a hierarchy, or changes version lifecycle state.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "staging", "lifecycle", "write"),
    ), apply_bop_staging_lifecycle_change)


__all__ = ["OPERATIONS", "apply_bop_staging_lifecycle_change", "register_bop_staging_lifecycle_change_capability"]
