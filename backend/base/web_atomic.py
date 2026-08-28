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
    "base.identity.role.assign.atomic",
    "base.saved_view.create",
    "base.saved_view.update",
    "base.saved_view.copy",
    "base.saved_view.delete",
    "base.self_annotation.change.apply",
}
_PERMISSIONS = {
    "base.authorization.grant.list": ("system.user.manage",),
    "base.authorization.grant.create": ("system.user.manage",),
    "base.authorization.grant.revoke": ("system.user.manage",),
    "base.identity.directory.feishu.sync": ("system.tech_config",),
    "base.identity.admin_user.list": ("system.user.manage",),
    "base.identity.role.assign.atomic": ("system.user.manage",),
}


def _actor(context: object) -> dict[str, Any]:
    roles = tuple(getattr(context, "active_roles", ()) or ())
    team_gid = getattr(context, "team_gid", None)
    role = next(
        (item for item in ("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member", "external") if item in roles),
        "external",
    )
    return {
        "gid": str(getattr(context, "user_gid", "")),
        "system_role": role,
        "org_role": role,
        "is_active": True,
        "tenant_gid": str(team_gid) if team_gid else "",
        "team_gids": [str(team_gid)] if team_gid else [],
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


def _structural_error(exc: Exception) -> CapabilityBusinessError:
    return CapabilityBusinessError(getattr(exc, "code", "provider_failed"), str(exc))


def _organization_teams(_payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.structural_web import StructuralWebError, list_organization_teams
    try:
        return list_organization_teams(actor=_actor(context))
    except StructuralWebError as exc:
        raise _structural_error(exc) from exc


def _teams(_payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.structural_web import StructuralWebError, list_teams
    try:
        return list_teams(actor=_actor(context))
    except StructuralWebError as exc:
        raise _structural_error(exc) from exc


def _annotation_batch(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.structural_web import StructuralWebError, annotation_batch
    try:
        return annotation_batch(actor=_actor(context), item_gids=payload["item_gids"])
    except StructuralWebError as exc:
        raise _structural_error(exc) from exc


def _annotation_get(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.self_annotations import SelfAnnotationError, SelfAnnotationService
    try:
        return SelfAnnotationService().get(actor=_actor(context), item_gid=payload["item_gid"])
    except SelfAnnotationError as exc:
        raise _structural_error(exc) from exc


def _annotation_search(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.self_annotations import SelfAnnotationError, SelfAnnotationService
    try:
        return SelfAnnotationService().search(actor=_actor(context), query=payload)
    except SelfAnnotationError as exc:
        raise _structural_error(exc) from exc


def _annotation_change(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.self_annotations import SelfAnnotationError, SelfAnnotationService
    try:
        return SelfAnnotationService().apply_change(actor=_actor(context), command=payload)
    except SelfAnnotationError as exc:
        raise _structural_error(exc) from exc


def _identity_profile(_payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.identity_profile import IdentityProfileService
    return IdentityProfileService().get_current(actor=_actor(context))


def _admin_users(_payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.structural_web import StructuralWebError, list_admin_users
    try:
        return list_admin_users(actor=_actor(context))
    except StructuralWebError as exc:
        raise _structural_error(exc) from exc


def _assign_role(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.structural_web import StructuralWebError, assign_user_role
    try:
        return assign_user_role(actor=_actor(context), **payload)
    except StructuralWebError as exc:
        raise _structural_error(exc) from exc


def _saved_view_search(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.saved_views import SavedViewError, SavedViewService
    try:
        return SavedViewService().search(actor=_actor(context), query=payload)
    except SavedViewError as exc:
        raise _structural_error(exc) from exc


def _saved_view_create(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.saved_views import SavedViewError, SavedViewService
    try:
        return SavedViewService().create(actor=_actor(context), command=payload)
    except SavedViewError as exc:
        raise _structural_error(exc) from exc


def _saved_view_update(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.saved_views import SavedViewError, SavedViewService
    try:
        command = {key: value for key, value in payload.items() if key != "view_gid"}
        return SavedViewService().update(actor=_actor(context), view_gid=payload["view_gid"], command=command)
    except SavedViewError as exc:
        raise _structural_error(exc) from exc


def _saved_view_copy(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.saved_views import SavedViewError, SavedViewService
    try:
        command = {key: value for key, value in payload.items() if key != "view_gid"}
        return SavedViewService().copy(actor=_actor(context), view_gid=payload["view_gid"], command=command)
    except SavedViewError as exc:
        raise _structural_error(exc) from exc


def _saved_view_delete(payload: dict[str, Any], context: object) -> dict[str, Any]:
    from backend.base.saved_views import SavedViewError, SavedViewService
    try:
        command = {key: value for key, value in payload.items() if key != "view_gid"}
        return SavedViewService().delete(actor=_actor(context), view_gid=payload["view_gid"], command=command)
    except SavedViewError as exc:
        raise _structural_error(exc) from exc


HANDLERS: dict[str, Callable[[dict[str, Any], object], dict[str, Any]]] = {
    "base.authorization.grant.list": _list_grants,
    "base.authorization.grant.create": _create_grant,
    "base.authorization.grant.revoke": _revoke_grant,
    "base.notification.preference.atomic.get": _get_preferences,
    "base.notification.preference.atomic.update": _update_preferences,
    "base.identity.directory.feishu.sync": _sync_feishu,
    "base.plugin.installed.list": _installed_plugins,
    "base.identity.user.search": _search_users,
    "base.organization.team.directory.list": _organization_teams,
    "base.team.directory.list": _teams,
    "base.self_annotation.batch.get": _annotation_batch,
    "base.self_annotation.record.get": _annotation_get,
    "base.self_annotation.search": _annotation_search,
    "base.self_annotation.change.apply": _annotation_change,
    "base.identity.session.profile.get": _identity_profile,
    "base.identity.admin_user.list": _admin_users,
    "base.identity.role.assign.atomic": _assign_role,
    "base.saved_view.search": _saved_view_search,
    "base.saved_view.create": _saved_view_create,
    "base.saved_view.update": _saved_view_update,
    "base.saved_view.copy": _saved_view_copy,
    "base.saved_view.delete": _saved_view_delete,
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
        handler = lambda payload, context, _id=capability_id: invoke_atomic(_id, payload, context)
        if capability_id in {"base.identity.role.assign.atomic", "base.saved_view.create", "base.saved_view.update", "base.saved_view.copy", "base.saved_view.delete", "base.self_annotation.change.apply"}:
            handler.__capability_transactional__ = True
        register_capability(registry, spec, handler)


__all__ = ["HANDLERS", "invoke_atomic", "register_atomic_web_capabilities"]
