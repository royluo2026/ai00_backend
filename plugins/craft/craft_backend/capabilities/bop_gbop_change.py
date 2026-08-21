"""Governed BOP-to-GBOP matching confirmation and auto-link writes."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

OPERATIONS = ("match_confirm", "auto_link")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_bop_gbop_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    from ..routers._bop import gbop as legacy
    actor = {"gid": context.user_gid, "name": context.user_gid, "org_role": "member"}
    if operation == "match_confirm":
        pbom_gid = _required(payload, "pbom_gid")
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise ValueError("matches must be an array")
        body = legacy.GbopMatchConfirmBody(matches=matches)
        return {"data": legacy._legacy_gbop_match_confirm(pbom_gid, body, actor)}
    bop_gid = _required(payload, "bop_gid")
    return {"data": legacy._legacy_gbop_auto_link(bop_gid, actor)}


def register_bop_gbop_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.gbop.change.apply", owner="craft",
        description="Confirm staged GBOP matches or auto-link confirmed matches into a BOP version.",
        use_when="A governed Craft consumer confirms GBOP matches or applies the confirmed auto-link batch.",
        do_not_use_when="The request only previews matches or reads PBOM versions.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "bop", "gbop", "write"),
    ), apply_bop_gbop_change)


__all__ = ["OPERATIONS", "apply_bop_gbop_change", "register_bop_gbop_change_capability"]
