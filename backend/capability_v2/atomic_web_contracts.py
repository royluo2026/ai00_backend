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
TEAM_ITEM = obj(
    {"gid": STRING, "name": {"type": "string", "maxLength": 512}, "is_active": BOOL,
     "parent_team_gid": OPT_STRING, "created_at": {"type": "string", "maxLength": 64}},
    ("gid", "name", "is_active", "parent_team_gid", "created_at"),
)
ORG_TEAM_ITEM = obj(
    {**TEAM_ITEM["properties"], "feishu_dept_id": OPT_STRING},
    ("gid", "name", "is_active", "parent_team_gid", "created_at", "feishu_dept_id"),
)
ANNOTATION_SUMMARY = obj(
    {"item_gid": STRING, "status": {"type": "string", "maxLength": 64},
     "schedule": {"type": "string", "maxLength": 128}, "has_note": BOOL,
     "attach_count": {"type": "integer", "minimum": 0, "maximum": 100}},
    ("item_gid", "status", "schedule", "has_note", "attach_count"),
)
ADMIN_USER = obj(
    {"gid": STRING, "name": {"type": "string", "maxLength": 512},
     "email": {"type": "string", "maxLength": 512}, "avatar_url": {"type": "string", "maxLength": 2048},
     "system_role": {"type": "string", "maxLength": 64}, "org_role": {"type": "string", "maxLength": 64},
     "external_subtype": OPT_STRING, "team_id": OPT_STRING, "is_active": BOOL,
     "created_at": {"type": "string", "maxLength": 64}},
    ("gid", "name", "email", "avatar_url", "system_role", "org_role", "external_subtype", "team_id", "is_active", "created_at"),
)
FILTER_VALUE = {"anyOf": [{"type": "string", "maxLength": 2000}, {"type": "number"}, {"type": "boolean"}, {"type": "null"}, {"type": "array", "maxItems": 100, "items": {"type": ["string", "number", "boolean", "null"]}}]}
SAVED_VIEW_CONFIG = obj(
    {
        "field_gids": {"type": "array", "minItems": 1, "maxItems": 200, "items": STRING},
        "sort": {"type": "array", "maxItems": 20, "items": obj({"field_gid": STRING, "direction": {"type": "string", "enum": ["asc", "desc"]}}, ("field_gid", "direction"))},
        "filters": {"type": "array", "maxItems": 50, "items": obj({"field_gid": STRING, "operator": {"type": "string", "enum": ["eq", "neq", "contains", "in", "gt", "gte", "lt", "lte"]}, "value": FILTER_VALUE}, ("field_gid", "operator", "value"))},
        "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
        "presentation": {"type": "string", "enum": ["table", "kanban", "calendar"]},
    },
    ("field_gids", "sort", "filters", "page_size", "presentation"),
)
RESTORE = obj({"available": BOOL, "deleted_by": STRING, "deleted_at": {"type": "string", "maxLength": 64}}, ("available", "deleted_by", "deleted_at"))
SAVED_VIEW = obj(
    {
        "gid": STRING, "name": STRING, "module": {"type": "string", "maxLength": 255}, "list_gid": OPT_STRING,
        "owner_gid": STRING, "config": SAVED_VIEW_CONFIG, "revision": {"type": "integer", "minimum": 1},
        "deleted": BOOL, "share_scope": {"type": "string", "enum": ["private", "team", "shared"]},
        "grants": {"type": "array", "maxItems": 200, "items": STRING}, "restore": {"type": ["object", "null"], "properties": RESTORE["properties"], "required": RESTORE["required"], "additionalProperties": False},
    },
    ("gid", "name", "module", "list_gid", "owner_gid", "config", "revision", "deleted", "share_scope", "grants", "restore"),
)


ROUTE_CAPABILITIES: dict[tuple[str, str], dict[str, Any]] = {
    ("GET", "/api/views"): {
        "id": "base.saved_view.search",
        "schema": obj({"module": {"type": "string", "maxLength": 255}, "list_gid": OPT_STRING}),
        "output_schema": obj({"views": {"type": "array", "maxItems": 500, "items": SAVED_VIEW}}, ("views",)),
    },
    ("POST", "/api/views"): {
        "id": "base.saved_view.create",
        "schema": obj({"name": STRING, "module": {"type": "string", "maxLength": 255}, "list_gid": OPT_STRING, "config": SAVED_VIEW_CONFIG, "share_scope": {"type": "string", "enum": ["private", "team", "shared"]}, "idempotency_key": STRING}, ("name", "config", "share_scope", "idempotency_key")),
        "output_schema": obj({"view": SAVED_VIEW}, ("view",)),
    },
    ("PATCH", "/api/views/{dynamic}"): {
        "id": "base.saved_view.update",
        "schema": obj({"view_gid": STRING, "expected_revision": {"type": "integer", "minimum": 1}, "name": STRING, "module": {"type": "string", "maxLength": 255}, "list_gid": OPT_STRING, "config": SAVED_VIEW_CONFIG, "share_scope": {"type": "string", "enum": ["private", "team", "shared"]}, "idempotency_key": STRING}, ("view_gid", "expected_revision", "name", "config", "idempotency_key")),
        "output_schema": obj({"view": SAVED_VIEW}, ("view",)),
    },
    ("DELETE", "/api/views/{dynamic}"): {
        "id": "base.saved_view.delete",
        "schema": obj({"view_gid": STRING, "expected_revision": {"type": "integer", "minimum": 1}, "idempotency_key": STRING}, ("view_gid", "expected_revision", "idempotency_key")),
        "output_schema": obj({"view": SAVED_VIEW}, ("view",)),
    },
    ("POST", "/api/views/{dynamic}/copy"): {
        "id": "base.saved_view.copy",
        "schema": obj({"view_gid": STRING, "name": STRING, "idempotency_key": STRING}, ("view_gid", "name", "idempotency_key")),
        "output_schema": obj({"view": SAVED_VIEW}, ("view",)),
    },
    ("GET", "/api/org/teams"): {
        "id": "base.organization.team.directory.list",
        "schema": obj({}),
        "output_schema": obj({"teams": {"type": "array", "maxItems": 1000, "items": ORG_TEAM_ITEM}}, ("teams",)),
    },
    ("GET", "/api/teams"): {
        "id": "base.team.directory.list",
        "schema": obj({}),
        "output_schema": obj({"success": BOOL, "data": {"type": "array", "maxItems": 1000, "items": TEAM_ITEM}}, ("success", "data")),
    },
    ("GET", "/api/self_ann/batch"): {
        "id": "base.self_annotation.batch.get",
        "schema": obj({"item_gids": {"type": "array", "minItems": 1, "maxItems": 500, "items": STRING}}, ("item_gids",)),
        "output_schema": obj({"items": {"type": "array", "maxItems": 500, "items": ANNOTATION_SUMMARY}}, ("items",)),
    },
    ("GET", "/api/users"): {
        "id": "base.identity.admin_user.list",
        "schema": obj({}),
        "output_schema": obj({"success": BOOL, "data": {"type": "array", "maxItems": 1000, "items": ADMIN_USER}}, ("success", "data")),
    },
    ("PATCH", "/api/users/{dynamic}/role"): {
        "id": "base.identity.role.assign.atomic",
        "schema": obj({"user_gid": STRING, "new_role": {"type": "string", "enum": ["super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member", "external"]}, "external_subtype": OPT_STRING}, ("user_gid", "new_role", "external_subtype")),
        "output_schema": obj({"success": BOOL, "data": ADMIN_USER}, ("success", "data")),
    },
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
    "base.saved_view.search": {"module": "", "list_gid": None},
    "base.saved_view.create": {"name": "Open", "config": {"field_gids": ["field_1"], "sort": [{"field_gid": "field_1", "direction": "asc"}], "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}], "page_size": 50, "presentation": "table"}, "share_scope": "private", "idempotency_key": "idem-1"},
    "base.saved_view.update": {"view_gid": "view_1", "expected_revision": 1, "name": "Open", "config": {"field_gids": ["field_1"], "sort": [{"field_gid": "field_1", "direction": "asc"}], "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}], "page_size": 50, "presentation": "table"}, "idempotency_key": "idem-2"},
    "base.saved_view.copy": {"view_gid": "view_1", "name": "Copy", "idempotency_key": "idem-3"},
    "base.saved_view.delete": {"view_gid": "view_1", "expected_revision": 1, "idempotency_key": "idem-4"},
    "base.organization.team.directory.list": {},
    "base.team.directory.list": {},
    "base.self_annotation.batch.get": {"item_gids": ["item_1"]},
    "base.identity.admin_user.list": {},
    "base.identity.role.assign.atomic": {"user_gid": "user_1", "new_role": "member", "external_subtype": None},
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
    "base.saved_view.search": {"views": []},
    "base.saved_view.create": {"view": {"gid": "view_1", "name": "Open", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"field_gids": ["field_1"], "sort": [{"field_gid": "field_1", "direction": "asc"}], "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}], "page_size": 50, "presentation": "table"}, "revision": 1, "deleted": False, "share_scope": "private", "grants": [], "restore": None}},
    "base.saved_view.update": {"view": {"gid": "view_1", "name": "Open", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"field_gids": ["field_1"], "sort": [{"field_gid": "field_1", "direction": "asc"}], "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}], "page_size": 50, "presentation": "table"}, "revision": 2, "deleted": False, "share_scope": "private", "grants": [], "restore": None}},
    "base.saved_view.copy": {"view": {"gid": "view_2", "name": "Copy", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"field_gids": ["field_1"], "sort": [{"field_gid": "field_1", "direction": "asc"}], "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}], "page_size": 50, "presentation": "table"}, "revision": 1, "deleted": False, "share_scope": "private", "grants": [], "restore": None}},
    "base.saved_view.delete": {"view": {"gid": "view_1", "name": "Open", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"field_gids": ["field_1"], "sort": [{"field_gid": "field_1", "direction": "asc"}], "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}], "page_size": 50, "presentation": "table"}, "revision": 2, "deleted": True, "share_scope": "private", "grants": [], "restore": {"available": True, "deleted_by": "user_1", "deleted_at": "transaction"}}},
    "base.organization.team.directory.list": {"teams": []},
    "base.team.directory.list": {"success": True, "data": []},
    "base.self_annotation.batch.get": {"items": []},
    "base.identity.admin_user.list": {"success": True, "data": []},
    "base.identity.role.assign.atomic": {"success": True, "data": {"gid": "user_1", "name": "", "email": "", "avatar_url": "", "system_role": "member", "org_role": "member", "external_subtype": None, "team_id": None, "is_active": True, "created_at": ""}},
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
    ("GET", "/api/self_ann/{dynamic}"): "The response contains attachment records without a governed nested attachment contract.",
    ("PUT", "/api/self_ann/{dynamic}"): "The request contains attachment records without a governed nested attachment contract.",
    ("GET", "/api/self_ann/list"): "The response contains attachment records without a governed nested attachment contract.",
    ("GET", "/api/users/me"): "The profile contains dynamic grants and permissions without a closed exact output contract.",
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
