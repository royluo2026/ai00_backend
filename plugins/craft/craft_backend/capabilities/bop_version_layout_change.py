"""Governed BOP version layout metadata mutation."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec

from ..data.connection import get_craft_conn


def apply_bop_version_layout_change(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    version_gid = str(payload.get("version_gid") or "").strip()
    if not version_gid:
        raise ValueError("version_gid is required")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
        if not cur.fetchone():
            raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
        cur.execute(
            "UPDATE workmanship_bop_bop_versions SET meta=JSON_SET(IFNULL(meta,'{}'),'$.view_config',CAST(%s AS JSON)), updated_at=NOW() WHERE gid=%s",
            (json.dumps(config, ensure_ascii=False), version_gid),
        )
        conn.commit()
    return {"data": {"success": True, "version_gid": version_gid}}


def register_bop_version_layout_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.version.layout.change.apply", owner="craft",
        description="Update the bounded shared layout configuration for a BOP version.",
        use_when="A governed Craft consumer changes a BOP version's shared canvas layout metadata.",
        do_not_use_when="The request changes BOP entities, lifecycle state, or snapshot contents.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["version_gid", "config"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "version", "layout", "write"),
    ), apply_bop_version_layout_change)


__all__ = ["apply_bop_version_layout_change", "register_bop_version_layout_change_capability"]
