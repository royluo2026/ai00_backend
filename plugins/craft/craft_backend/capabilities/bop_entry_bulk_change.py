"""Governed bulk/import/history mutations for BOP entries."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityExecutionBudget, CapabilitySpec

OPERATIONS = (
    "create", "purge", "import_tc", "copy", "copy_from_gbop",
    "auto_link", "entity_detail.patch", "history.rollback",
)


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _actor(context: CapabilityContext) -> dict[str, Any]:
    return {"gid": context.user_gid, "name": context.user_gid, "org_role": "member"}


def apply_bop_entry_bulk_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    if operation == "create":
        version_gid = str(payload.get("version_gid") or payload.get("bop_version_gid") or "").strip()
        if not version_gid:
            raise ValueError("version_gid is required")
        from ..routers._bop import entries as legacy
        body = legacy.CreateEntryBody(**{k: v for k, v in payload.items() if k not in {"operation"}})
        return {"data": legacy._legacy_create_entry(body, _actor(context))}
    if operation == "purge":
        version_gid = _required(payload, "version_gid")
        from ..routers._bop import entries as legacy
        return {"data": legacy._legacy_purge_version_entries(version_gid, legacy.PurgeEntriesBody(mode=payload.get("mode", "soft")), _actor(context))}
    if operation == "import_tc":
        version_gid = _required(payload, "version_gid")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("rows must be an array")
        from ..routers._bop import entries as legacy
        return {"data": legacy._legacy_import_tc_entries(version_gid, legacy.ImportTcBody(rows=rows), _actor(context))}
    if operation in {"copy", "copy_from_gbop"}:
        version_gid = _required(payload, "version_gid")
        source_gid = _required(payload, "source_gid")
        from ..routers._bop import entries as legacy
        fn = legacy._legacy_copy_entries_from_gbop if operation == "copy_from_gbop" else legacy._legacy_copy_entries_from
        return {"data": fn(version_gid, source_gid, _actor(context))}
    if operation == "auto_link":
        version_gid = _required(payload, "version_gid")
        from ..routers._bop import entries as legacy
        body = legacy.AutoLinkBody(step=payload.get("step", "all"), mode=payload.get("mode", "incremental"))
        return {"data": legacy._legacy_auto_link_entries(version_gid, body, _actor(context))}
    if operation == "entity_detail.patch":
        from ..routers._bop import entries as legacy
        body = legacy.EntityPatchBody(link_type=_required(payload, "link_type"), ref_gid=_required(payload, "ref_gid"), fields=payload.get("fields") or {})
        return {"data": legacy._legacy_patch_entity_detail(body, _actor(context))}
    from ..routers._bop import entries as legacy
    return {"data": legacy._legacy_rollback_entry_history(_required(payload, "gid"), _required(payload, "log_gid"), _actor(context))}


def register_bop_entry_bulk_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.entry.bulk.change.apply", owner="craft",
        description="Create, import, copy, auto-link, purge, patch, or rollback BOP entries through one governed change boundary.",
        use_when="A governed Craft consumer performs a multi-entry or entry-history mutation.",
        do_not_use_when="The request only updates or deletes one existing entry or only changes an entry link.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        execution_budget=CapabilityExecutionBudget(memory_class="large", max_input_bytes=64 * 1024 * 1024),
        tags=("craft", "bop", "entry", "bulk", "write"),
    ), apply_bop_entry_bulk_change)


__all__ = ["OPERATIONS", "apply_bop_entry_bulk_change", "register_bop_entry_bulk_change_capability"]
