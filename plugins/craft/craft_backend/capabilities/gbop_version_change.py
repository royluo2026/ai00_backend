"""Governed GBOP version lifecycle and fork mutations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

OPERATIONS = ("create", "update", "freeze", "archive_family", "unarchive_family", "fork")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_gbop_version_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    from ..routers import gbop as legacy
    actor = {"gid": context.user_gid, "name": context.user_gid, "team_id": context.team_gid, "org_role": "member"}
    if operation == "create":
        body = legacy.CreateVersionBody(**{k: v for k, v in payload.items() if k not in {"operation"}})
        return legacy._legacy_create_version(body, actor)
    if operation == "update":
        gid = _required(payload, "gid")
        return legacy._legacy_update_version(gid, legacy.UpdateVersionBody(**(payload.get("updates") or {})), actor)
    if operation == "freeze":
        return legacy._legacy_freeze_version(_required(payload, "gid"), actor)
    if operation in {"archive_family", "unarchive_family"}:
        family_gid = _required(payload, "family_gid")
        fn = legacy._legacy_archive_family if operation == "archive_family" else legacy._legacy_unarchive_family
        return fn(family_gid, actor)
    source_gid = _required(payload, "source_gid")
    body = legacy.ForkBody(**{k: v for k, v in payload.items() if k not in {"operation", "source_gid"}})
    return legacy._legacy_fork_version(source_gid, body, actor)


def register_gbop_version_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.gbop.version.change.apply", owner="craft",
        description="Create, update, freeze, archive, unarchive, or fork a GBOP version through one governed boundary.",
        use_when="A governed Craft consumer changes GBOP version lifecycle or creates a derived version.",
        do_not_use_when="The request changes entries, process cards, operation cards, links, or imports.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "gbop", "version", "write"),
    ), apply_gbop_version_change)


__all__ = ["OPERATIONS", "apply_gbop_version_change", "register_gbop_version_change_capability"]
