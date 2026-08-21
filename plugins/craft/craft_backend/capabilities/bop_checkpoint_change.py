"""Governed creation of immutable BOP line checkpoints."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_craft_conn


def apply_bop_checkpoint_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation != "create":
        raise ValueError("operation must be create")
    version_gid = str(payload.get("version_gid") or "").strip()
    line_gid = str(payload.get("line_gid") or "").strip()
    if not version_gid:
        raise ValueError("version_gid is required")
    if not line_gid:
        raise ValueError("line_gid is required")

    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        if not cur.fetchone():
            raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
        cur.execute(
            "WITH RECURSIVE subtree AS ("
            "SELECT gid FROM workmanship_bop_bop_entries WHERE gid=%s AND version_gid=%s AND is_deleted=FALSE "
            "UNION ALL SELECT e.gid FROM workmanship_bop_bop_entries e JOIN subtree s ON e.parent_gid=s.gid "
            "WHERE e.version_gid=%s AND e.is_deleted=FALSE) SELECT gid FROM subtree",
            (line_gid, version_gid, version_gid),
        )
        scope_gids = [str(row["gid"] if isinstance(row, dict) else dict(row)["gid"]) for row in cur.fetchall()]
        if not scope_gids:
            raise CapabilityBusinessError("resource_not_found", f"line {line_gid} has no active entries")
        placeholders = ",".join(["%s"] * len(scope_gids))
        cur.execute(f"SELECT * FROM workmanship_bop_bop_entries WHERE gid IN ({placeholders}) AND is_deleted=FALSE", scope_gids)
        entries = [dict(row) for row in cur.fetchall()]
        cur.execute(f"SELECT * FROM workmanship_bop_bop_entry_links WHERE entry_gid IN ({placeholders}) AND is_deleted=FALSE", scope_gids)
        links = [dict(row) for row in cur.fetchall()]
        checkpoint_gid = str(next_gid())
        cur.execute(
            "INSERT INTO workmanship_bop_bop_line_checkpoints (gid,version_gid,line_gid,label,created_by,created_by_name,snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (checkpoint_gid, version_gid, line_gid, payload.get("label"), context.user_gid, context.user_gid, json.dumps({"entries": entries, "links": links}, default=str)),
        )
        conn.commit()
    return {"data": {"gid": checkpoint_gid, "label": payload.get("label")}}


def register_bop_checkpoint_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.lifecycle.checkpoint.change.apply", owner="craft",
        description="Create an immutable snapshot checkpoint for a BOP line subtree.",
        use_when="A governed Craft consumer records a named checkpoint before further line changes.",
        do_not_use_when="The request restores, undoes, or redoes a checkpoint or history batch.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "version_gid", "line_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "lifecycle", "checkpoint", "write"),
    ), apply_bop_checkpoint_change)


__all__ = ["apply_bop_checkpoint_change", "register_bop_checkpoint_change_capability"]
