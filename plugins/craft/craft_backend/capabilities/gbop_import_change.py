"""Governed imports into GBOP versions."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

OPERATIONS = ("import_vpps_parts", "import_entries")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_gbop_import_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    version_gid = _required(payload, "version_gid")
    from ..routers import gbop as legacy
    actor = {"gid": context.user_gid, "name": context.user_gid, "team_id": context.team_gid, "org_role": "member"}
    if operation == "import_vpps_parts":
        return legacy._legacy_import_vpps_parts(version_gid, legacy.ImportVppsPartsBody(levels=payload.get("levels", [1, 2, 3])), actor)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("entries must be an array")
    return legacy._legacy_import_entries(version_gid, legacy.ImportEntriesBody(entries=entries), actor)


def register_gbop_import_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.gbop.import.change.apply", owner="craft",
        description="Import bounded VPPS parts or parsed entries into a GBOP version.",
        use_when="A governed Craft consumer imports validated VPPS or entry rows into an editable GBOP version.",
        do_not_use_when="The request imports Teamcenter Excel binary content or mutates individual GBOP entities.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "version_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "gbop", "import", "write"),
    ), apply_gbop_import_change)


__all__ = ["OPERATIONS", "apply_gbop_import_change", "register_gbop_import_change_capability"]
