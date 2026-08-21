"""Governed restoration of a BOP line subtree from a checkpoint snapshot."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec

from ..data.connection import get_craft_conn


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def apply_bop_checkpoint_rollback(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    version_gid = _required(payload, "version_gid")
    line_gid = _required(payload, "line_gid")
    checkpoint_gid = _required(payload, "checkpoint_gid")

    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT snapshot FROM workmanship_bop_bop_line_checkpoints WHERE gid=%s AND version_gid=%s AND line_gid=%s", (checkpoint_gid, version_gid, line_gid))
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"checkpoint {checkpoint_gid} does not exist for this version and line")
        snapshot = row.get("snapshot") if isinstance(row, dict) else dict(row)["snapshot"]
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except (TypeError, ValueError) as exc:
                raise CapabilityBusinessError("invalid_state", "checkpoint snapshot is not valid JSON") from exc
        snapshot = dict(snapshot or {})
        entries = [dict(item) for item in snapshot.get("entries", [])]
        links = [dict(item) for item in snapshot.get("links", [])]

        cur.execute(
            "WITH RECURSIVE subtree AS (SELECT gid FROM workmanship_bop_bop_entries WHERE gid=%s AND version_gid=%s AND is_deleted=FALSE UNION ALL SELECT e.gid FROM workmanship_bop_bop_entries e JOIN subtree s ON e.parent_gid=s.gid WHERE e.version_gid=%s AND e.is_deleted=FALSE) SELECT gid FROM subtree",
            (line_gid, version_gid, version_gid),
        )
        scope = [str(item["gid"] if isinstance(item, dict) else dict(item)["gid"]) for item in cur.fetchall()]
        if scope:
            placeholders = ",".join(["%s"] * len(scope))
            cur.execute(f"UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE,deleted_at=NOW() WHERE gid IN ({placeholders})", scope)
            cur.execute(f"UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE,deleted_at=NOW() WHERE entry_gid IN ({placeholders})", scope)

        for entry in entries:
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entries (gid,version_gid,parent_gid,node_type,sort_order,level,ai00_level,title,vpps,vpps_desc,parent_bop_title,child_vpps,owner_gid,meta,is_deleted,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,NOW(),NOW()) ON DUPLICATE KEY UPDATE is_deleted=FALSE,deleted_at=NULL,parent_gid=VALUES(parent_gid),sort_order=VALUES(sort_order),node_type=VALUES(node_type),title=VALUES(title),vpps=VALUES(vpps),vpps_desc=VALUES(vpps_desc),parent_bop_title=VALUES(parent_bop_title),child_vpps=VALUES(child_vpps),meta=VALUES(meta),updated_at=NOW()",
                (entry.get("gid"), entry.get("version_gid") or version_gid, entry.get("parent_gid"), entry.get("node_type"), entry.get("sort_order", 0), entry.get("level", 0), entry.get("ai00_level"), entry.get("title"), entry.get("vpps"), entry.get("vpps_desc"), entry.get("parent_bop_title"), _json(entry.get("child_vpps", [])), entry.get("owner_gid"), _json(entry.get("meta", {}))),
            )
        for link in links:
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entry_links (gid,entry_gid,version_gid,link_type,entity_gid,is_primary,is_inherited,is_deleted) VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE) ON DUPLICATE KEY UPDATE is_deleted=FALSE,deleted_at=NULL,entry_gid=VALUES(entry_gid),link_type=VALUES(link_type),entity_gid=VALUES(entity_gid),is_primary=VALUES(is_primary)",
                (link.get("gid"), link.get("entry_gid"), link.get("version_gid") or version_gid, link.get("link_type"), link.get("entity_gid"), bool(link.get("is_primary", False)), bool(link.get("is_inherited", False))),
            )
        conn.commit()
    return {"data": {"restored_entries": len(entries), "restored_links": len(links), "checkpoint_gid": checkpoint_gid}}


def register_bop_checkpoint_rollback_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.lifecycle.checkpoint.rollback.apply", owner="craft",
        description="Restore a BOP line subtree and links from a selected checkpoint snapshot.",
        use_when="A governed Craft consumer explicitly restores one line to a checkpoint.",
        do_not_use_when="The request creates a checkpoint or undoes/redoes an operation-history batch.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["version_gid", "line_gid", "checkpoint_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "lifecycle", "checkpoint", "rollback", "write"),
    ), apply_bop_checkpoint_rollback)


__all__ = ["apply_bop_checkpoint_rollback", "register_bop_checkpoint_rollback_capability"]
