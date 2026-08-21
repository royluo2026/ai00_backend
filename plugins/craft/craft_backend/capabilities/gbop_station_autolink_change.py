"""Governed station auto-link apply and undo operations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

OPERATIONS = ("apply", "undo")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_gbop_station_autolink_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    bop_gid = _required(payload, "bop_gid")
    from ..routers import gbop as legacy
    actor = {"gid": context.user_gid, "name": context.user_gid, "role": "member", "system_role": "member"}
    if operation == "apply":
        body = legacy.StationAutolinkBody(pbom_version_gid=payload.get("pbom_version_gid"), line_gids=payload.get("line_gids"))
        return {"data": legacy._legacy_station_autolink(bop_gid, body, actor)}
    return {"data": legacy._legacy_station_autolink_undo(bop_gid, payload.get("mode", "soft"), actor)}


def register_gbop_station_autolink_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.gbop.station_autolink.change.apply", owner="craft",
        description="Apply or undo governed station auto-link changes for a BOP version.",
        use_when="A governed Craft consumer applies or reverses station auto-link results.",
        do_not_use_when="The request only previews candidates.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "bop_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "gbop", "station", "autolink", "write"),
    ), apply_gbop_station_autolink_change)


__all__ = ["OPERATIONS", "apply_gbop_station_autolink_change", "register_gbop_station_autolink_change_capability"]
