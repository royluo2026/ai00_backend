"""Exact Base browser outcomes backed by the existing Base handlers."""
from __future__ import annotations

import inspect
import json
from typing import Any, Callable

from backend.capability_v2.atomic_web_contracts import OUTPUT_SCHEMA, ROUTE_CAPABILITIES
from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from . import contracts
from .provider import register_capability


def _user(context: object) -> dict[str, Any]:
    roles = tuple(getattr(context, "active_roles", ()) or ())
    role = next((item for item in ("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member") if item in roles), "member")
    return {
        "gid": str(getattr(context, "user_gid", "")), "team_id": getattr(context, "team_gid", None),
        "team_gid": getattr(context, "team_gid", None), "system_role": role, "org_role": role, "role": role,
    }


def _json_value(value: str, expected: type, label: str) -> Any:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(decoded, expected):
        raise ValueError(f"{label} must encode {expected.__name__}")
    return decoded


def _list_grants(*, user_gid=None, user=None):
    from backend.platform_sdk.base_web_outcomes import list_grants
    return list_grants(user_gid=user_gid, current_user=user)


def _create_grant(*, grantee_gid, grant_type, scope_gid=None, expires_at=None, note="", user=None):
    from backend.platform_sdk.base_web_outcomes import GrantBody, create_grant
    return create_grant(GrantBody(grantee_gid=grantee_gid, grant_type=grant_type, scope_gid=scope_gid, expires_at=expires_at, note=note), current_user=user)


def _revoke_grant(*, gid, user=None):
    from backend.platform_sdk.base_web_outcomes import delete_grant
    return delete_grant(gid, current_user=user)


def _get_preferences(*, user=None):
    from backend.platform_sdk.base_web_outcomes import get_prefs
    return get_prefs(current_user=user)


def _update_preferences(*, preferences, user=None):
    from backend.platform_sdk.base_web_outcomes import update_prefs
    return update_prefs(preferences, current_user=user)


def _sync_feishu(*, department_id=None, user=None):
    from backend.platform_sdk.base_web_outcomes import SyncFromFeishuBody, sync_from_feishu
    return sync_from_feishu(SyncFromFeishuBody(dept_id=department_id), current_user=user)


def _org_teams(*, user=None):
    from backend.platform_sdk.base_web_outcomes import list_org_teams
    return list_org_teams(current_user=user)


def _installed_plugins(*, user=None):
    from backend.platform_sdk.base_web_outcomes import list_plugins
    return list_plugins(current_user=user)


def _annotation_get(*, item_gid, user=None):
    from backend.platform_sdk.base_web_outcomes import get_annotation
    return get_annotation(item_gid, user=user)


def _annotation_upsert(*, item_gid, annotation, user=None):
    from backend.platform_sdk.base_web_outcomes import SelfAnnotationBody, upsert_annotation
    normalized = dict(annotation)
    if "self_attachments_json" in normalized:
        normalized["self_attachments"] = _json_value(normalized.pop("self_attachments_json"), list, "self_attachments_json")
    return upsert_annotation(item_gid, SelfAnnotationBody.model_validate(normalized), user=user)


def _annotation_batch(*, item_gids, user=None):
    from backend.platform_sdk.base_web_outcomes import get_annotation_batch
    return get_annotation_batch(",".join(item_gids), user=user)


def _annotation_list(*, module="", user=None):
    from backend.platform_sdk.base_web_outcomes import list_annotations
    return list_annotations(module, user=user)


def _teams(*, user=None):
    from backend.platform_sdk.base_web_outcomes import list_teams
    return list_teams(current_user=user)


def _users(*, user=None):
    from backend.platform_sdk.base_web_outcomes import list_users
    return list_users(current_user=user)


def _assign_role(*, user_gid, new_role, external_subtype=None, user=None):
    from backend.platform_sdk.base_web_outcomes import AssignRoleBody, assign_role
    return assign_role(user_gid, AssignRoleBody(new_role=new_role, external_subtype=external_subtype), current_user=user)


def _session(*, user=None):
    from backend.platform_sdk.base_web_outcomes import get_me
    return get_me(current_user=user)


def _search_users(*, query, limit, user=None):
    from backend.platform_sdk.base_web_outcomes import search_users
    return search_users(q=query, limit=limit, current_user=user)


def _views(*, module="", list_gid=None, user=None):
    from backend.platform_sdk.base_web_outcomes import list_views
    return list_views(module=module, list_gid=list_gid, user=user)


def _create_view(*, module, config_json, name="未命名视图", list_gid=None, is_shared=False, user=None):
    from backend.platform_sdk.base_web_outcomes import CreateViewBody, create_view
    config = _json_value(config_json, dict, "config_json")
    return create_view(CreateViewBody(name=name, module=module, list_gid=list_gid, config=config, is_shared=is_shared), user=user)


def _delete_view(*, gid, user=None):
    from backend.platform_sdk.base_web_outcomes import delete_view
    return delete_view(gid, user=user)


def _update_view(*, gid, changes, user=None):
    from backend.platform_sdk.base_web_outcomes import UpdateViewBody, update_view
    normalized = dict(changes)
    if "config_json" in normalized:
        normalized["config"] = _json_value(normalized.pop("config_json"), dict, "config_json")
    return update_view(gid, UpdateViewBody.model_validate(normalized), user=user)


def _copy_view(*, gid, user=None):
    from backend.platform_sdk.base_web_outcomes import copy_view
    return copy_view(gid, user=user)


HANDLERS: dict[str, Callable[..., Any]] = {
    "base.authorization.grant.list": _list_grants, "base.authorization.grant.create": _create_grant,
    "base.authorization.grant.revoke": _revoke_grant, "base.notification.preference.atomic.get": _get_preferences,
    "base.notification.preference.atomic.update": _update_preferences, "base.identity.directory.feishu.sync": _sync_feishu,
    "base.team.directory.list": _org_teams, "base.plugin.installed.list": _installed_plugins,
    "base.annotation.get": _annotation_get, "base.annotation.upsert": _annotation_upsert,
    "base.annotation.batch.get": _annotation_batch, "base.annotation.list": _annotation_list,
    "base.team.list": _teams, "base.identity.user.list": _users,
    "base.identity.user.role.assign": _assign_role, "base.identity.session.get.atomic": _session,
    "base.identity.user.search": _search_users, "base.saved_view.list": _views,
    "base.saved_view.create": _create_view, "base.saved_view.delete": _delete_view,
    "base.saved_view.update": _update_view, "base.saved_view.copy": _copy_view,
}


def invoke_atomic(capability_id: str, payload: dict[str, Any], context: object) -> Any:
    handler = HANDLERS[capability_id]
    available = {**payload, "user_gid": getattr(context, "user_gid", ""), "user": _user(context), "context": context}
    parameters = inspect.signature(handler).parameters
    return handler(**{name: value for name, value in available.items() if name in parameters})


def register_atomic_web_capabilities(registry: Any) -> None:
    definitions = [value for value in ROUTE_CAPABILITIES.values() if value["id"].startswith("base.")]
    for definition in definitions:
        capability_id, input_schema = definition["id"], definition["schema"]
        is_write = capability_id not in {
            "base.authorization.grant.list", "base.notification.preference.atomic.get", "base.team.directory.list",
            "base.plugin.installed.list", "base.annotation.get", "base.annotation.batch.get", "base.annotation.list",
            "base.team.list", "base.identity.user.list", "base.identity.session.get.atomic",
            "base.identity.user.search", "base.saved_view.list",
        }
        contracts.INPUT_SCHEMAS[capability_id] = input_schema
        contracts.OUTPUT_SCHEMAS[capability_id] = OUTPUT_SCHEMA
        spec = CapabilitySpec(
            id=capability_id, owner="base", description=f"Execute exact Base outcome {capability_id}.",
            use_when="A browser consumer needs exactly this Base-owned outcome.",
            do_not_use_when="The request selects another operation or domain.",
            risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
            confirmation=("admin" if capability_id in {"base.identity.directory.feishu.sync", "base.identity.user.role.assign"} else "user") if is_write else "none",
            idempotent=True, permissions=("base.write",) if is_write else ("base.read",),
            input_schema=input_schema, output_schema=OUTPUT_SCHEMA, tags=("base", "atomic", "web"),
        )
        register_capability(registry, spec, lambda payload, context, _id=capability_id: {"result_json": json.dumps(invoke_atomic(_id, payload, context), ensure_ascii=False, default=str)})


__all__ = ["HANDLERS", "invoke_atomic", "register_atomic_web_capabilities"]
