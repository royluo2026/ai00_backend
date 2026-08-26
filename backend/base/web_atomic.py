"""Exact Base browser outcomes backed by public owner services."""
from __future__ import annotations

from typing import Any, Callable

from backend.capability_v2.atomic_web_contracts import ROUTE_CAPABILITIES
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityRisk, CapabilitySpec

from . import contracts
from .provider import register_capability


_WRITES = {
    "base.authorization.grant.create",
    "base.authorization.grant.revoke",
    "base.notification.preference.atomic.update",
    "base.identity.directory.feishu.sync",
}
_PERMISSIONS = {
    "base.authorization.grant.list": ("system.user.manage",),
    "base.authorization.grant.create": ("system.user.manage",),
    "base.authorization.grant.revoke": ("system.user.manage",),
    "base.identity.directory.feishu.sync": ("system.tech_config",),
}


def _actor(context: object) -> dict[str, Any]:
    roles = tuple(getattr(context, "active_roles", ()) or ())
    role = next(
        (item for item in ("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member", "external") if item in roles),
        "external",
    )
    return {
        "gid": str(getattr(context, "user_gid", "")),
        "system_role": role,
        "org_role": role,
        "is_active": True,
    }


def _grant_error(exc: Exception) -> CapabilityBusinessError:
    return CapabilityBusinessError(
        getattr(exc, "code", "provider_failed"),
        str(exc),
    )


def _list_grants(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.grant_service import GrantServiceError, list_grants
    try:
        return list_grants(actor=_actor(context), user_gid=payload.get("user_gid"))
    except GrantServiceError as exc:
        raise _grant_error(exc) from exc


def _create_grant(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.grant_service import GrantServiceError, create_grant
    try:
        return create_grant(actor=_actor(context), **payload)
    except GrantServiceError as exc:
        raise _grant_error(exc) from exc


def _revoke_grant(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.grant_service import GrantServiceError, revoke_grant
    try:
        return revoke_grant(actor=_actor(context), gid=payload["gid"])
    except GrantServiceError as exc:
        raise _grant_error(exc) from exc


def _get_preferences(_payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.platform_sdk.notification_preferences import get_notification_preferences
    return {"success": True, "data": get_notification_preferences(str(getattr(context, "user_gid", "")))}


def _update_preferences(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.platform_sdk.notification_preferences import update_notification_preferences
    return {
        "success": True,
        "data": update_notification_preferences(
            str(getattr(context, "user_gid", "")), payload["preferences"]
        ),
    }


def _sync_feishu(payload: dict[str, Any], context: object) -> dict[str, Any]:
    if "super_admin" not in set(getattr(context, "active_roles", ()) or ()):
        raise CapabilityBusinessError("permission_denied", "仅超管可操作")
    from backend.services.org_sync_service import sync_all_from_feishu
    return {"ok": True, **sync_all_from_feishu(root_dept_id=payload.get("department_id"))}


def _installed_plugins(_payload: dict[str, Any], _context: object) -> dict[str, Any]:
    from backend.base.plugin_inventory import list_installed_plugins
    return list_installed_plugins()


def _search_users(payload: dict[str, Any], _context: object) -> dict[str, Any]:
    from backend.services.user_service import search_users
    values = search_users(payload["query"], payload["limit"])
    return {"success": True, "data": [
        {
            "gid": str(user["gid"]),
            "name": str(user.get("name") or ""),
            "email": str(user.get("email") or ""),
            "avatar_url": str(user.get("avatar_url") or ""),
        }
        for user in values
    ]}


HANDLERS: dict[str, Callable[[dict[str, Any], object], dict[str, Any]]] = {
    "base.authorization.grant.list": _list_grants,
    "base.authorization.grant.create": _create_grant,
    "base.authorization.grant.revoke": _revoke_grant,
    "base.notification.preference.atomic.get": _get_preferences,
    "base.notification.preference.atomic.update": _update_preferences,
    "base.identity.directory.feishu.sync": _sync_feishu,
    "base.plugin.installed.list": _installed_plugins,
    "base.identity.user.search": _search_users,
}


def invoke_atomic(capability_id: str, payload: dict[str, Any], context: object) -> Any:
    return HANDLERS[capability_id](payload, context)


def register_atomic_web_capabilities(registry: Any) -> None:
    for definition in ROUTE_CAPABILITIES.values():
        capability_id = definition["id"]
        input_schema = definition["schema"]
        output_schema = definition["output_schema"]
        is_write = capability_id in _WRITES
        contracts.INPUT_SCHEMAS[capability_id] = input_schema
        contracts.OUTPUT_SCHEMAS[capability_id] = output_schema
        spec = CapabilitySpec(
            id=capability_id,
            owner="base",
            description=f"Execute exact Base outcome {capability_id}.",
            use_when="A browser consumer needs exactly this Base-owned outcome.",
            do_not_use_when="The request selects another operation or domain.",
            risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
            confirmation=("admin" if capability_id == "base.identity.directory.feishu.sync" else "user") if is_write else "none",
            idempotent=True,
            permissions=_PERMISSIONS.get(capability_id, ()),
            input_schema=input_schema,
            output_schema=output_schema,
            tags=("base", "atomic", "web"),
        )
        register_capability(
            registry,
            spec,
            lambda payload, context, _id=capability_id: invoke_atomic(_id, payload, context),
        )


__all__ = ["HANDLERS", "invoke_atomic", "register_atomic_web_capabilities"]
