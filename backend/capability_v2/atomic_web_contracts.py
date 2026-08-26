"""Reviewed exact contracts for the safe Task 3B.3c browser outcomes."""
from __future__ import annotations

from typing import Any


def obj(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


STRING = {"type": "string", "minLength": 1, "maxLength": 512}
TEXT = {"type": "string", "maxLength": 2000}
OPT_STRING = {"type": ["string", "null"], "maxLength": 512}
BOOL = {"type": "boolean"}
PREFERENCES = obj(
    {
        "scope_approved": BOOL,
        "scope_rejected": BOOL,
        "item_status": BOOL,
        "new_follower": BOOL,
    },
    ("scope_approved", "scope_rejected", "item_status", "new_follower"),
)
GRANT_ITEM = obj(
    {
        "gid": STRING,
        "grantee_gid": STRING,
        "grant_type": STRING,
        "scope_gid": OPT_STRING,
        "granted_by": STRING,
        "expires_at": OPT_STRING,
        "note": TEXT,
        "granted_at": OPT_STRING,
        "grantee_name": OPT_STRING,
    },
    ("gid", "grantee_gid", "grant_type", "scope_gid", "granted_by", "expires_at", "note", "granted_at"),
)
PLUGIN_ITEM = obj(
    {
        "plugin_id": {"type": "string", "maxLength": 256},
        "name": {"type": "string", "maxLength": 512},
        "version": {"type": "string", "maxLength": 128},
        "category": {"type": "string", "maxLength": 128},
        "enabled": BOOL,
        "builtin": BOOL,
    },
    ("plugin_id", "name", "version", "category", "enabled", "builtin"),
)
USER_SEARCH_ITEM = obj(
    {
        "gid": STRING,
        "name": {"type": "string", "maxLength": 512},
        "email": {"type": "string", "maxLength": 512},
        "avatar_url": {"type": "string", "maxLength": 2048},
    },
    ("gid", "name", "email", "avatar_url"),
)
SYNC_OUTPUT = obj(
    {
        "ok": BOOL,
        "created": {"type": "integer", "minimum": 0},
        "updated": {"type": "integer", "minimum": 0},
        "dept_synced": {"type": "integer", "minimum": 0},
        "departments": {"type": "integer", "minimum": 0},
        "manual_teams_preserved": BOOL,
    },
    ("ok", "created", "updated", "dept_synced", "departments", "manual_teams_preserved"),
)


ROUTE_CAPABILITIES: dict[tuple[str, str], dict[str, Any]] = {
    ("GET", "/api/grants"): {
        "id": "base.authorization.grant.list",
        "schema": obj({"user_gid": OPT_STRING}),
        "output_schema": obj({"grants": {"type": "array", "maxItems": 500, "items": GRANT_ITEM}}, ("grants",)),
    },
    ("POST", "/api/grants"): {
        "id": "base.authorization.grant.create",
        "schema": obj({"grantee_gid": STRING, "grant_type": STRING, "scope_gid": OPT_STRING, "expires_at": OPT_STRING, "note": TEXT}, ("grantee_gid", "grant_type")),
        "output_schema": obj({"grant": GRANT_ITEM}, ("grant",)),
    },
    ("DELETE", "/api/grants/{dynamic}"): {
        "id": "base.authorization.grant.revoke",
        "schema": obj({"gid": STRING}, ("gid",)),
        "output_schema": obj({"ok": BOOL}, ("ok",)),
    },
    ("GET", "/api/notifications/prefs"): {
        "id": "base.notification.preference.atomic.get",
        "schema": obj({}),
        "output_schema": obj({"success": BOOL, "data": PREFERENCES}, ("success", "data")),
    },
    ("PATCH", "/api/notifications/prefs"): {
        "id": "base.notification.preference.atomic.update",
        "schema": obj({"preferences": obj({"scope_approved": BOOL, "scope_rejected": BOOL, "item_status": BOOL, "new_follower": BOOL})}, ("preferences",)),
        "output_schema": obj({"success": BOOL, "data": PREFERENCES}, ("success", "data")),
    },
    ("POST", "/api/org/sync-from-feishu"): {
        "id": "base.identity.directory.feishu.sync",
        "schema": obj({"department_id": OPT_STRING}),
        "output_schema": SYNC_OUTPUT,
    },
    ("GET", "/api/plugin/list"): {
        "id": "base.plugin.installed.list",
        "schema": obj({}),
        "output_schema": obj({"success": BOOL, "data": {"type": "array", "maxItems": 500, "items": PLUGIN_ITEM}}, ("success", "data")),
    },
    ("GET", "/api/users/search"): {
        "id": "base.identity.user.search",
        "schema": obj({"query": {"type": "string", "maxLength": 200}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ("query", "limit")),
        "output_schema": obj({"success": BOOL, "data": {"type": "array", "maxItems": 50, "items": USER_SEARCH_ITEM}}, ("success", "data")),
    },
}

EXAMPLES: dict[str, dict[str, Any]] = {
    "base.authorization.grant.list": {"user_gid": None},
    "base.authorization.grant.create": {"grantee_gid": "usr_2", "grant_type": "team_admin", "scope_gid": "team_1", "expires_at": None, "note": ""},
    "base.authorization.grant.revoke": {"gid": "grant_1"},
    "base.notification.preference.atomic.get": {},
    "base.notification.preference.atomic.update": {"preferences": {"item_status": True}},
    "base.identity.directory.feishu.sync": {"department_id": None},
    "base.plugin.installed.list": {},
    "base.identity.user.search": {"query": "", "limit": 10},
}

EXAMPLE_OUTPUTS: dict[str, dict[str, Any]] = {
    "base.authorization.grant.list": {"grants": []},
    "base.authorization.grant.create": {"grant": {"gid": "grant_1", "grantee_gid": "usr_2", "grant_type": "team_admin", "scope_gid": "team_1", "granted_by": "usr_1", "expires_at": None, "note": "", "granted_at": None}},
    "base.authorization.grant.revoke": {"ok": True},
    "base.notification.preference.atomic.get": {"success": True, "data": {"scope_approved": True, "scope_rejected": True, "item_status": True, "new_follower": True}},
    "base.notification.preference.atomic.update": {"success": True, "data": {"scope_approved": True, "scope_rejected": True, "item_status": True, "new_follower": True}},
    "base.identity.directory.feishu.sync": {"ok": True, "created": 0, "updated": 0, "dept_synced": 0, "departments": 0, "manual_teams_preserved": True},
    "base.plugin.installed.list": {"success": True, "data": []},
    "base.identity.user.search": {"success": True, "data": []},
}

UNSAFE_REASONS = {
    ("POST", "/api/plugin/install"): "The arbitrary-URL installer route has no production handler and is not equivalent to signed marketplace installation.",
    ("DELETE", "/api/plugin/uninstall/{dynamic}"): "The unrestricted legacy uninstall route has no production handler and cannot bypass marketplace lifecycle controls.",
    ("GET", "/api/org/teams"): "The response contains unbounded team config that cannot be published as a closed exact schema.",
    ("GET", "/api/self_ann/{dynamic}"): "The response contains attachment records without a governed nested attachment contract.",
    ("PUT", "/api/self_ann/{dynamic}"): "The request contains attachment records without a governed nested attachment contract.",
    ("GET", "/api/self_ann/batch"): "The dynamic item-gid keyed result cannot be represented by the closed production schema validator.",
    ("GET", "/api/self_ann/list"): "The response contains attachment records without a governed nested attachment contract.",
    ("GET", "/api/teams"): "The response contains unbounded team config that cannot be published as a closed exact schema.",
    ("GET", "/api/users"): "The legacy service returns unprojected user records including non-public fields; no exact safe output exists.",
    ("PATCH", "/api/users/{dynamic}/role"): "The legacy service returns an unprojected user record; no exact safe output exists without changing REST semantics.",
    ("GET", "/api/users/me"): "The profile contains dynamic grants and permissions without a closed exact output contract.",
    ("GET", "/api/views"): "Saved-view config is intentionally dynamic and has no governed closed nested contract.",
    ("POST", "/api/views"): "Saved-view config is intentionally dynamic and has no governed closed nested contract.",
    ("DELETE", "/api/views/{dynamic}"): "The object-ownership check has no public owner-service boundary independent of dynamic saved-view config.",
    ("PATCH", "/api/views/{dynamic}"): "Saved-view config is intentionally dynamic and has no governed closed nested contract.",
    ("POST", "/api/views/{dynamic}/copy"): "The copied result depends on dynamic saved-view config without a governed closed nested contract.",
    ("PUT", "/api/rules/{dynamic}"): "Rule definition changes contain dynamic rule_definition data without a governed closed nested contract.",
    ("DELETE", "/api/craft_lib/equipments/{dynamic}"): "No delete provider exists; the available obsolete transition is a different lifecycle outcome.",
    ("DELETE", "/api/craft_lib/fixtures/{dynamic}"): "No delete provider exists; the available obsolete transition is a different lifecycle outcome.",
    ("GET", "/api/rule-engine/check-entry"): "No entry-check provider exists; CEL evaluation and BOP audit are different outcomes.",
    ("POST", "/api/rules/{dynamic}/activate"): "No mutable-rule activation provider exists; immutable release activation is a different lifecycle outcome.",
    ("POST", "/api/rules/{dynamic}/deviations"): "No legacy deviation provider exists; governed release waiver creation has a different evidence contract.",
    ("POST", "/api/rules/{dynamic}/suspend"): "No mutable-rule suspension handler or domain service exists.",
    ("POST", "/api/approval/orders/{dynamic}/reject"): "The Project outcome omits the legacy notification publication side effect.",
    ("POST", "/api/flows/test-node"): "No node-test handler or runtime service exists in the Agent provider.",
    ("POST", "/api/skills/canvas-options"): "No bounded canvas-option resolver exists in the Agent provider.",
    ("POST", "/api/skills/execute-canvas"): "No canvas execution provider exists; generic run mutation is not provider-equivalent.",
    ("POST", "/api/skills/resume-canvas"): "No pause-token resume provider exists; generic run mutation is not provider-equivalent.",
}

for _method, _route in (
    ("GET", "/api/ext-datasources"), ("POST", "/api/ext-datasources"),
    ("PATCH", "/api/ext-datasources/{dynamic}"), ("GET", "/api/ext-datasources/{dynamic}/tables"),
    ("POST", "/api/ext-datasources/{dynamic}/test"), ("GET", "/api/ext-field-mappings"),
    ("PUT", "/api/ext-field-mappings/batch"), ("GET", "/api/ext-mappings"),
    ("POST", "/api/ext-mappings"), ("GET", "/api/ext-mappings/{dynamic}/columns"),
    ("POST", "/api/ext-mappings/{dynamic}/import"), ("GET", "/api/ext-mappings/{dynamic}/preview"),
):
    UNSAFE_REASONS[(_method, _route)] = "The legacy endpoint has no production handler; the governed Integration provider has a non-equivalent contract."


__all__ = ["EXAMPLES", "EXAMPLE_OUTPUTS", "ROUTE_CAPABILITIES", "UNSAFE_REASONS"]
