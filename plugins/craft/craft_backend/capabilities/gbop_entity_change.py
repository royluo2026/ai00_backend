"""Governed GBOP entry, process, operation, and link mutations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

OPERATIONS = (
    "entry.create", "entry.update", "entry.delete",
    "process.create", "process.update", "process.delete",
    "operation.create", "operation.update", "operation.delete",
    "link.create", "link.delete",
)


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_gbop_entity_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    from ..routers import gbop as legacy
    actor = {"gid": context.user_gid, "name": context.user_gid, "team_id": context.team_gid, "org_role": "member"}
    kind, action = operation.split(".")
    if kind == "entry":
        if action == "create":
            return legacy._legacy_create_entry(legacy.CreateEntryBody(**{k: v for k, v in payload.items() if k not in {"operation"}}), actor)
        gid = _required(payload, "gid")
        if action == "update":
            return legacy._legacy_update_entry(gid, legacy.UpdateEntryBody(**(payload.get("updates") or {})), actor)
        return legacy._legacy_delete_entry(gid, actor)
    if kind == "process":
        if action == "create":
            return legacy._legacy_create_process(legacy.CreateProcessBody(**{k: v for k, v in payload.items() if k not in {"operation"}}), actor)
        gid = _required(payload, "gid")
        if action == "update":
            return legacy._legacy_update_process(gid, legacy.UpdateProcessBody(**(payload.get("updates") or {})), actor)
        return legacy._legacy_delete_process(gid, actor)
    if kind == "operation":
        if action == "create":
            return legacy._legacy_create_operation(legacy.CreateOperationBody(**{k: v for k, v in payload.items() if k not in {"operation"}}), actor)
        gid = _required(payload, "gid")
        if action == "update":
            return legacy._legacy_update_operation(gid, legacy.UpdateOperationBody(**(payload.get("updates") or {})), actor)
        return legacy._legacy_delete_operation(gid, actor)
    if action == "create":
        return legacy._legacy_create_entry_link(legacy.CreateEntryLinkBody(**{k: v for k, v in payload.items() if k not in {"operation"}}), actor)
    return legacy._legacy_delete_entry_link(_required(payload, "gid"), actor)


def register_gbop_entity_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.gbop.entity.change.apply", owner="craft",
        description="Create, update, delete GBOP entries, process cards, operation cards, and entry links.",
        use_when="A governed Craft consumer mutates one GBOP entity or link.",
        do_not_use_when="The request changes version lifecycle, imports external data, or only reads GBOP projections.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "gbop", "entity", "write"),
    ), apply_gbop_entity_change)


__all__ = ["OPERATIONS", "apply_gbop_entity_change", "register_gbop_entity_change_capability"]
