"""Governed BOP version freeze and unfreeze mutations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec

from ..data.connection import get_craft_conn
from ..routers._bop._helpers import _clear_snapshots, _snapshot_links


OPERATIONS = ("freeze", "unfreeze")


def apply_bop_version_freeze_change(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    version_gid = str(payload.get("version_gid") or "").strip()
    if not version_gid:
        raise ValueError("version_gid is required")

    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
        status = row.get("status") if isinstance(row, dict) else dict(row)["status"]
        expected = "active" if operation == "freeze" else "baseline"
        if status != expected:
            action = "frozen" if operation == "freeze" else "unfrozen"
            raise CapabilityBusinessError("invalid_state", f"only {expected} versions can be {action} (current: {status})")
        if operation == "freeze":
            _snapshot_links(cur, version_gid)
            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET status='baseline', frozen_at=NOW(), updated_at=NOW() WHERE gid=%s",
                (version_gid,),
            )
            next_status = "baseline"
        else:
            _clear_snapshots(cur, version_gid)
            cur.execute(
                "UPDATE workmanship_bop_bop_versions SET status='active', frozen_at=NULL, updated_at=NOW() WHERE gid=%s",
                (version_gid,),
            )
            next_status = "active"
        cur.execute("SELECT * FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        result = cur.fetchone()
        conn.commit()
    return {"data": dict(result) if result else {"gid": version_gid, "status": next_status}}


def register_bop_version_freeze_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.version.freeze.change.apply", owner="craft",
        description="Freeze an active BOP version with link snapshots or unfreeze a baseline version.",
        use_when="A governed Craft consumer changes a BOP version's frozen baseline state.",
        do_not_use_when="The request creates a version snapshot/fork, promotes a snapshot, or publishes a version.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "version_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "version", "freeze", "write"),
    ), apply_bop_version_freeze_change)


__all__ = ["OPERATIONS", "apply_bop_version_freeze_change", "register_bop_version_freeze_change_capability"]
