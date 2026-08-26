"""Reviewed exact contracts for the Task 3B.3c browser migration wave."""
from __future__ import annotations

from typing import Any


STRING = {"type": "string", "minLength": 1, "maxLength": 512}
OPT_STRING = {"type": ["string", "null"], "maxLength": 512}
BOOL = {"type": "boolean"}
SMALL_OBJECT = {"type": "object", "maxProperties": 50, "additionalProperties": True}
ITEMS = {"type": "array", "maxItems": 500, "items": SMALL_OBJECT}
STRINGS = {"type": "array", "maxItems": 500, "items": STRING}
JSON_TEXT = {"type": "string", "maxLength": 1000000}
OUTPUT_SCHEMA = {
    "type": "object", "required": ["result_json"],
    "properties": {"result_json": {"type": "string", "maxLength": 4000000}},
    "additionalProperties": False,
}


def obj(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


# One exact public outcome per route/method.  Shared adapters are transport
# reuse only; operation selection never appears in a public payload.
ROUTE_CAPABILITIES: dict[tuple[str, str], dict[str, Any]] = {
    ("GET", "/api/grants"): {"id": "base.authorization.grant.list", "schema": obj({"user_gid": OPT_STRING})},
    ("POST", "/api/grants"): {"id": "base.authorization.grant.create", "schema": obj({"grantee_gid": STRING, "grant_type": STRING, "scope_gid": OPT_STRING, "expires_at": OPT_STRING, "note": {"type": "string", "maxLength": 2000}}, ("grantee_gid", "grant_type"))},
    ("DELETE", "/api/grants/{dynamic}"): {"id": "base.authorization.grant.revoke", "schema": obj({"gid": STRING}, ("gid",))},
    ("GET", "/api/notifications/prefs"): {"id": "base.notification.preference.atomic.get", "schema": obj({})},
    ("PATCH", "/api/notifications/prefs"): {"id": "base.notification.preference.atomic.update", "schema": obj({"preferences": obj({"scope_approved": BOOL, "scope_rejected": BOOL, "item_status": BOOL, "new_follower": BOOL})}, ("preferences",))},
    ("POST", "/api/org/sync-from-feishu"): {"id": "base.identity.directory.feishu.sync", "schema": obj({"department_id": OPT_STRING})},
    ("GET", "/api/org/teams"): {"id": "base.team.directory.list", "schema": obj({})},
    ("GET", "/api/plugin/list"): {"id": "base.plugin.installed.list", "schema": obj({})},
    ("GET", "/api/self_ann/{dynamic}"): {"id": "base.annotation.get", "schema": obj({"item_gid": STRING}, ("item_gid",))},
    ("PUT", "/api/self_ann/{dynamic}"): {"id": "base.annotation.upsert", "schema": obj({"item_gid": STRING, "annotation": obj({"module": {"type": "string", "maxLength": 128}, "item_title": {"type": "string", "maxLength": 512}, "self_status": {"type": "string", "maxLength": 64}, "self_schedule": {"type": "string", "maxLength": 128}, "self_note": {"type": "string", "maxLength": 20000}, "self_attachments_json": JSON_TEXT})}, ("item_gid", "annotation"))},
    ("GET", "/api/self_ann/batch"): {"id": "base.annotation.batch.get", "schema": obj({"item_gids": STRINGS}, ("item_gids",))},
    ("GET", "/api/self_ann/list"): {"id": "base.annotation.list", "schema": obj({"module": {"type": "string", "maxLength": 128}})},
    ("GET", "/api/teams"): {"id": "base.team.list", "schema": obj({})},
    ("GET", "/api/users"): {"id": "base.identity.user.list", "schema": obj({})},
    ("PATCH", "/api/users/{dynamic}/role"): {"id": "base.identity.user.role.assign", "schema": obj({"user_gid": STRING, "new_role": STRING, "external_subtype": OPT_STRING}, ("user_gid", "new_role"))},
    ("GET", "/api/users/me"): {"id": "base.identity.session.get.atomic", "schema": obj({})},
    ("GET", "/api/users/search"): {"id": "base.identity.user.search", "schema": obj({"query": {"type": "string", "maxLength": 200}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ("query", "limit"))},
    ("GET", "/api/views"): {"id": "base.saved_view.list", "schema": obj({"module": {"type": "string", "maxLength": 128}, "list_gid": OPT_STRING})},
    ("POST", "/api/views"): {"id": "base.saved_view.create", "schema": obj({"name": {"type": "string", "maxLength": 512}, "module": STRING, "list_gid": OPT_STRING, "config_json": JSON_TEXT, "is_shared": BOOL}, ("module", "config_json"))},
    ("DELETE", "/api/views/{dynamic}"): {"id": "base.saved_view.delete", "schema": obj({"gid": STRING}, ("gid",))},
    ("PATCH", "/api/views/{dynamic}"): {"id": "base.saved_view.update", "schema": obj({"gid": STRING, "changes": obj({"name": {"type": "string", "maxLength": 512}, "config_json": JSON_TEXT, "is_shared": BOOL, "list_gid": OPT_STRING})}, ("gid", "changes"))},
    ("POST", "/api/views/{dynamic}/copy"): {"id": "base.saved_view.copy", "schema": obj({"gid": STRING}, ("gid",))},
    ("PUT", "/api/rules/{dynamic}"): {"id": "craft.rule.definition.update", "schema": obj({"gid": STRING, "changes_json": JSON_TEXT}, ("gid", "changes_json"))},
}

EXAMPLES: dict[str, dict[str, Any]] = {
    "base.authorization.grant.list": {"user_gid": None},
    "base.authorization.grant.create": {"grantee_gid": "usr_2", "grant_type": "team_admin", "scope_gid": "team_1", "expires_at": None, "note": ""},
    "base.authorization.grant.revoke": {"gid": "grant_1"},
    "base.notification.preference.atomic.get": {},
    "base.notification.preference.atomic.update": {"preferences": {"item_status": True}},
    "base.identity.directory.feishu.sync": {"department_id": None},
    "base.team.directory.list": {}, "base.plugin.installed.list": {},
    "base.annotation.get": {"item_gid": "item_1"},
    "base.annotation.upsert": {"item_gid": "item_1", "annotation": {"module": "task", "item_title": "T", "self_status": "todo", "self_schedule": "", "self_note": "", "self_attachments_json": "[]"}},
    "base.annotation.batch.get": {"item_gids": ["item_1"]},
    "base.annotation.list": {"module": "task"}, "base.team.list": {},
    "base.identity.user.list": {},
    "base.identity.user.role.assign": {"user_gid": "usr_2", "new_role": "member", "external_subtype": None},
    "base.identity.session.get.atomic": {},
    "base.identity.user.search": {"query": "", "limit": 10},
    "base.saved_view.list": {"module": "task", "list_gid": None},
    "base.saved_view.create": {"name": "View", "module": "task", "list_gid": None, "config_json": "{}", "is_shared": False},
    "base.saved_view.delete": {"gid": "view_1"},
    "base.saved_view.update": {"gid": "view_1", "changes": {"name": "View 2"}},
    "base.saved_view.copy": {"gid": "view_1"},
    "craft.rule.definition.update": {"gid": "rule_1", "changes_json": "{\"name\":\"Rule\"}"},
}

UNSAFE_REASONS = {
    ("POST", "/api/plugin/install"): "The arbitrary-URL installer route has no production handler and is not equivalent to signed marketplace installation.",
    ("DELETE", "/api/plugin/uninstall/{dynamic}"): "The unrestricted legacy uninstall route has no production handler and cannot bypass marketplace lifecycle controls.",
    ("DELETE", "/api/craft_lib/equipments/{dynamic}"): "No delete provider exists; the available obsolete transition is a different lifecycle outcome.",
    ("DELETE", "/api/craft_lib/fixtures/{dynamic}"): "No delete provider exists; the available obsolete transition is a different lifecycle outcome.",
    ("GET", "/api/rule-engine/check-entry"): "No entry-check provider exists; CEL evaluation and BOP audit are different outcomes.",
    ("POST", "/api/rules/{dynamic}/activate"): "No mutable-rule activation provider exists; immutable release activation is a different lifecycle.",
    ("POST", "/api/rules/{dynamic}/deviations"): "No legacy deviation provider exists; governed release waiver creation has a different evidence contract.",
    ("POST", "/api/rules/{dynamic}/suspend"): "No mutable-rule suspension handler or domain service exists.",
    ("POST", "/api/approval/orders/{dynamic}/reject"): "The Project outcome returns a notification side effect that the legacy adapter must publish; a direct atomic invocation would silently omit it and requires BFF or provider redesign.",
    ("POST", "/api/flows/test-node"): "No node-test handler or runtime service exists in the Agent provider.",
    ("POST", "/api/skills/canvas-options"): "No bounded canvas-option resolver exists in the Agent provider.",
    ("POST", "/api/skills/execute-canvas"): "No canvas execution provider exists; generic run mutation is not provider-equivalent.",
    ("POST", "/api/skills/resume-canvas"): "No pause-token resume provider exists; generic run mutation is not provider-equivalent.",
}

# All twelve legacy Integration endpoints are absent from production routing;
# the governed connector/mapping application has materially different revision,
# ownership, network and asynchronous contracts.
for _method, _route in (
    ("GET", "/api/ext-datasources"), ("POST", "/api/ext-datasources"),
    ("PATCH", "/api/ext-datasources/{dynamic}"), ("GET", "/api/ext-datasources/{dynamic}/tables"),
    ("POST", "/api/ext-datasources/{dynamic}/test"), ("GET", "/api/ext-field-mappings"),
    ("PUT", "/api/ext-field-mappings/batch"), ("GET", "/api/ext-mappings"),
    ("POST", "/api/ext-mappings"), ("GET", "/api/ext-mappings/{dynamic}/columns"),
    ("POST", "/api/ext-mappings/{dynamic}/import"), ("GET", "/api/ext-mappings/{dynamic}/preview"),
):
    UNSAFE_REASONS[(_method, _route)] = "The legacy endpoint has no production handler; the governed Integration provider has a non-equivalent owned/revisioned contract."


__all__ = ["EXAMPLES", "OUTPUT_SCHEMA", "ROUTE_CAPABILITIES", "UNSAFE_REASONS"]
