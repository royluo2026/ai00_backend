"""Governed BOP version publication and family archival mutations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec

from ..data.connection import get_craft_conn


OPERATIONS = ("publish", "archive_family", "unarchive_family")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_bop_version_lifecycle_change(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    key = "version_gid" if operation == "publish" else "family_gid"
    identifier = _required(payload, key)

    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            if operation == "publish":
                cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (identifier,))
                row = cur.fetchone()
                if not row:
                    raise CapabilityBusinessError("resource_not_found", f"BOP version {identifier} does not exist")
                status = row.get("status") if isinstance(row, dict) else dict(row)["status"]
                if status != "baseline":
                    raise CapabilityBusinessError("invalid_state", f"only baseline versions can be published (current: {status})")
                cur.execute(
                    "UPDATE workmanship_bop_bop_versions SET status='M', published_at=NOW(), updated_at=NOW() WHERE gid=%s",
                    (identifier,),
                )
                result = {"version_gid": identifier, "status": "M"}
            elif operation == "archive_family":
                cur.execute(
                    "UPDATE workmanship_bop_bop_versions SET status='archived', archived_at=NOW(), updated_at=NOW() "
                    "WHERE version_family_gid=%s AND status IN ('baseline','M') AND is_deleted=FALSE",
                    (identifier,),
                )
                result = {"family_gid": identifier, "archived_count": cur.rowcount}
            else:
                cur.execute(
                    "UPDATE workmanship_bop_bop_versions SET status=CASE WHEN published_at IS NOT NULL THEN 'M' ELSE 'baseline' END, "
                    "archived_at=NULL, updated_at=NOW() WHERE version_family_gid=%s AND status='archived' AND is_deleted=FALSE",
                    (identifier,),
                )
                result = {"family_gid": identifier, "unarchived_count": cur.rowcount}
        conn.commit()
    return {"data": result}


def register_bop_version_lifecycle_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.version.lifecycle.change.apply", owner="craft",
        description="Publish a BOP version or archive/unarchive a BOP version family.",
        use_when="A governed Craft consumer changes BOP version publication or family archival state.",
        do_not_use_when="The request freezes/unfreezes links, creates a snapshot, or changes draft content.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "version", "lifecycle", "write"),
    ), apply_bop_version_lifecycle_change)


__all__ = ["OPERATIONS", "apply_bop_version_lifecycle_change", "register_bop_version_lifecycle_change_capability"]
