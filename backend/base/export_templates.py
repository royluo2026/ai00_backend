"""Base-owned Provider for the reviewed export-template read surface."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityRisk,
    CapabilitySpec,
)
from backend.platform_sdk.export_templates import (
    create_export_template as _create_export_template,
    delete_export_template as _delete_export_template,
    list_export_templates as _list_export_templates,
    update_export_template as _update_export_template,
)

from .provider import register_capability


CAPABILITY_ID = "base.export_template.read"
CHANGE_CAPABILITY_ID = "base.export_template.change.apply"
MAX_ITEMS = 500


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "gid": str(row.get("gid") or ""),
        "name": str(row.get("name") or ""),
        "module": str(row.get("module") or ""),
        "owner_gid": str(row.get("owner_gid") or ""),
        "is_shared": bool(row.get("is_shared")),
        "config": _json_value(row.get("config") or {}),
        "created_at": _json_value(row.get("created_at")) or "",
        "updated_at": _json_value(row.get("updated_at")) or "",
    }


def list_export_templates(
    payload: dict[str, Any], context: CapabilityContext
) -> dict[str, Any]:
    module = str(payload.get("module") or "").strip()
    limit = int(payload.get("limit", MAX_ITEMS))
    if limit < 1 or limit > MAX_ITEMS:
        raise ValueError(f"limit must be between 1 and {MAX_ITEMS}")

    rows = list(_list_export_templates(context.user_gid, module))
    if len(rows) > MAX_ITEMS:
        raise CapabilityBusinessError(
            "response_limit_exceeded",
            "The export-template result exceeds the bounded response limit.",
            details={"limit": MAX_ITEMS, "count": len(rows)},
        )
    items = [_normalize_row(row) for row in rows[:limit]]
    return {"items": items, "total": len(items), "module": module}


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _is_admin(context: CapabilityContext) -> bool:
    return bool(set(context.active_roles or ()) & {"super_admin", "team_admin"})


def apply_export_template(
    payload: dict[str, Any], context: CapabilityContext
) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    user_gid = context.user_gid
    try:
        if operation == "create":
            name = str(payload.get("name") or "未命名模板")
            module = str(payload.get("module") or "*")
            config = payload.get("config") or {}
            if not isinstance(config, dict):
                raise ValueError("config must be an object")
            gid = _create_export_template(
                user_gid, name, module, config, bool(payload.get("is_shared", False))
            )
            return {"operation": operation, "gid": str(gid)}
        if operation == "update":
            gid = _required_text(payload, "gid")
            updates = payload.get("updates")
            if not isinstance(updates, dict):
                raise ValueError("updates must be an object")
            allowed = {"name", "module", "config", "is_shared"}
            unknown = set(updates) - allowed
            if unknown:
                raise ValueError(f"unsupported update fields: {', '.join(sorted(unknown))}")
            if "config" in updates and updates["config"] is not None and not isinstance(updates["config"], dict):
                raise ValueError("config must be an object")
            _update_export_template(gid, user_gid, _is_admin(context), updates)
            return {"operation": operation, "gid": gid}
        if operation == "delete":
            gid = _required_text(payload, "gid")
            _delete_export_template(gid, user_gid, _is_admin(context))
            return {"operation": operation, "gid": gid}
        raise ValueError("operation must be one of: create, update, delete")
    except LookupError as exc:
        raise CapabilityBusinessError("resource_not_found", str(exc)) from exc
    except PermissionError as exc:
        raise CapabilityBusinessError("permission_denied", str(exc)) from exc


def register_export_template_capability(registry: Any) -> None:
    register_capability(
        registry,
        CapabilitySpec(
            id=CAPABILITY_ID,
            owner="base",
            description="Read the caller-visible Base export templates.",
            use_when="A consumer needs export-template metadata owned by the Base Platform.",
            do_not_use_when="The consumer needs to create, update, or delete an export template.",
            risk=CapabilityRisk.READ,
            permissions=("base.read",),
            tags=("base", "export-template", "read"),
        ),
        list_export_templates,
    )
    register_capability(
        registry,
        CapabilitySpec(
            id=CHANGE_CAPABILITY_ID,
            owner="base",
            description="Create, update, or delete a Base export template.",
            use_when="A consumer needs a confirmed, idempotent export-template mutation.",
            do_not_use_when="The consumer only needs to list templates.",
            risk=CapabilityRisk.WRITE,
            confirmation="user",
            permissions=("base.write",),
            tags=("base", "export-template", "write"),
        ),
        apply_export_template,
    )


__all__ = [
    "CAPABILITY_ID",
    "CHANGE_CAPABILITY_ID",
    "MAX_ITEMS",
    "apply_export_template",
    "list_export_templates",
    "register_export_template_capability",
]
