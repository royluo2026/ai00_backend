"""Governed BOP entry-link attachment and detachment."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn
from ..routers._bop._helpers import _check_line_editable, _log_entry_op
from .resource_requirements import RESOURCE_TYPES_BY_LINK, validate_resource_link


OPERATIONS = ("attach", "detach")


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


def apply_bop_entry_link_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    if operation == "attach":
        entry_gid = _required(payload, "entry_gid")
        link_type = _required(payload, "link_type")
        entity_gid = _required(payload, "entity_gid")
    else:
        link_gid = _required(payload, "link_gid")

    with get_craft_conn() as conn, conn.cursor() as cur:
        if operation == "attach":
            cur.execute("SELECT version_gid FROM workmanship_bop_bop_entries WHERE gid=%s", (entry_gid,))
            entry = cur.fetchone()
            if not entry:
                raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
            version_gid = entry.get("version_gid") if isinstance(entry, dict) else dict(entry)["version_gid"]
            _ensure_editable(cur, version_gid, entry_gid, context)
            if link_type in RESOURCE_TYPES_BY_LINK:
                validate_resource_link(link_type, entity_gid, cur)
            link_gid = str(next_gid())
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entry_links "
                "(gid, entry_gid, version_gid, link_type, entity_gid, is_primary, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (link_gid, entry_gid, version_gid, link_type, entity_gid, bool(payload.get("is_primary", False)), context.user_gid),
            )
            _log_entry_op(
                cur, version_gid=version_gid, entry_gid=entry_gid, entry_title="", op_type="add_link",
                old_state=None, new_state={"link_type": link_type, "entity_gid": entity_gid, "is_primary": bool(payload.get("is_primary", False))},
                user_gid=context.user_gid, user_name=context.user_gid,
            )
            conn.commit()
            return {"data": {"gid": link_gid}}

        cur.execute(
            "SELECT l.entry_gid, e.version_gid, l.link_type, l.entity_gid, l.is_primary, e.title AS entry_title "
            "FROM workmanship_bop_bop_entry_links l JOIN workmanship_bop_bop_entries e ON e.gid=l.entry_gid WHERE l.gid=%s",
            (link_gid,),
        )
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"BOP entry link {link_gid} does not exist")
        row = dict(row)
        _ensure_editable(cur, row["version_gid"], row["entry_gid"], context)
        _log_entry_op(
            cur, version_gid=row["version_gid"], entry_gid=row["entry_gid"], entry_title=row.get("entry_title") or "", op_type="remove_link",
            old_state={"link_type": row["link_type"], "entity_gid": row["entity_gid"], "is_primary": row["is_primary"]}, new_state=None,
            user_gid=context.user_gid, user_name=context.user_gid,
        )
        cur.execute("DELETE FROM workmanship_bop_bop_entry_links WHERE gid=%s", (link_gid,))
        conn.commit()
    return {"data": {"gid": link_gid, "deleted": True}}


def register_bop_entry_link_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.entry_link.change.apply", owner="craft",
        description="Attach or detach a governed BOP entry link.",
        use_when="A Craft consumer changes the relationship between a BOP entry and a linked entity.",
        do_not_use_when="The request creates or edits a BOP entry, copies a hierarchy, or changes a version lifecycle.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "entry", "link", "write"),
    ), apply_bop_entry_link_change)


__all__ = ["OPERATIONS", "apply_bop_entry_link_change", "register_bop_entry_link_change_capability"]
