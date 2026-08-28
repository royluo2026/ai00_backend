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
PLUGIN_INSTALLATION = obj(
    {
        "plugin_id": STRING, "release_version": {"type": "string", "minLength": 1, "maxLength": 64},
        "state": {"type": "string", "enum": ["disabled", "uninstalled"]},
        "revision": {"type": "integer", "minimum": 1},
        "granted_capabilities": {"type": "array", "maxItems": 200, "items": STRING},
        "tenant_gid": STRING,
    },
    ("plugin_id", "release_version", "state", "revision", "granted_capabilities", "tenant_gid"),
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
ANNOTATION_ATTACHMENT = obj(
    {"attachment_gid": STRING, "media_type": {"type": "string", "maxLength": 128},
     "display_name": {"type": "string", "maxLength": 512},
     "size": {"type": "integer", "minimum": 0, "maximum": 52428800},
     "checksum": {"type": "string", "minLength": 71, "maxLength": 71, "pattern": "^sha256:[0-9a-f]{64}$"}},
    ("attachment_gid", "media_type", "display_name", "size", "checksum"),
)
ANNOTATION_RESTORE = obj({"available": BOOL, "deleted_by": STRING, "deleted_at": {"type": "string", "maxLength": 64}}, ("available", "deleted_by", "deleted_at"))
SELF_ANNOTATION = obj(
    {"item_gid": STRING, "status": {"type": "string", "maxLength": 64}, "schedule": OPT_STRING,
     "note": TEXT, "attachments": {"type": "array", "maxItems": 100, "items": ANNOTATION_ATTACHMENT},
     "revision": {"type": "integer", "minimum": 1}, "deleted": BOOL,
     "restore": {"type": ["object", "null"], "properties": ANNOTATION_RESTORE["properties"], "required": ANNOTATION_RESTORE["required"], "additionalProperties": False}},
    ("item_gid", "status", "schedule", "note", "attachments", "revision", "deleted", "restore"),
)
IDENTITY_PROFILE = obj(
    {"actor_gid": STRING, "display_name": {"type": "string", "maxLength": 512}, "tenant_gid": {"type": "string", "maxLength": 128},
     "team_gids": {"type": "array", "maxItems": 200, "items": STRING}, "locale": {"type": "string", "maxLength": 64},
     "timezone": {"type": "string", "maxLength": 128}, "permission_ids": {"type": "array", "maxItems": 1000, "items": STRING}},
    ("actor_gid", "display_name", "tenant_gid", "team_gids", "locale", "timezone", "permission_ids"),
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
        "columns": {"type": "array", "maxItems": 200, "items": obj({"key": STRING, "visible": BOOL, "order": {"type": "integer", "minimum": 0}, "width": {"type": "integer", "minimum": 40, "maximum": 2000}}, ("key", "visible", "order", "width"))},
        "filters": {"type": "array", "maxItems": 50, "items": obj({"id": STRING, "field": STRING, "op": {"type": "string", "enum": ["contains", "not_contains", "eq", "not_eq", "empty", "not_empty", "gt", "gte", "lt", "lte"]}, "value": FILTER_VALUE}, ("id", "field", "op", "value"))},
        "filterMode": {"type": "string", "enum": ["and", "or"]},
        "sorts": {"type": "array", "maxItems": 20, "items": obj({"field": STRING, "dir": {"type": "string", "enum": ["asc", "desc"]}}, ("field", "dir"))},
        "groupBy": OPT_STRING,
        "viewType": {"type": "string", "enum": ["grid", "tree"]},
        "treeParentField": OPT_STRING,
    },
    ("columns", "filters", "filterMode", "sorts", "groupBy", "viewType", "treeParentField"),
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
    ("POST", "/api/plugin/install"): {
        "id": "base.plugin.installation.request.create",
        "schema": obj({
            "plugin_id": {"type": "string", "minLength": 1, "maxLength": 255},
            "release_version": {"type": "string", "minLength": 1, "maxLength": 64},
            "release_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "requested_grants": {"type": "array", "maxItems": 200, "uniqueItems": True, "items": STRING},
            "idempotency_key": STRING,
        }, ("plugin_id", "release_version", "release_sha256", "requested_grants", "idempotency_key")),
        "output_schema": obj({"installation": PLUGIN_INSTALLATION}, ("installation",)),
    },
    ("DELETE", "/api/plugin/uninstall/{dynamic}"): {
        "id": "base.plugin.installation.transition.uninstall",
        "schema": obj({
            "plugin_id": {"type": "string", "minLength": 1, "maxLength": 255},
            "expected_revision": {"type": "integer", "minimum": 1},
            "retain_tenant_data": {"const": True}, "idempotency_key": STRING,
        }, ("plugin_id", "expected_revision", "retain_tenant_data", "idempotency_key")),
        "output_schema": obj({"installation": PLUGIN_INSTALLATION}, ("installation",)),
    },
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
    ("GET", "/api/self_ann/{dynamic}"): {
        "id": "base.self_annotation.record.get",
        "schema": obj({"item_gid": STRING}, ("item_gid",)),
        "output_schema": obj({"annotation": SELF_ANNOTATION}, ("annotation",)),
    },
    ("GET", "/api/self_ann/list"): {
        "id": "base.self_annotation.search",
        "schema": obj({"limit": {"type": "integer", "minimum": 1, "maximum": 200}, "status": OPT_STRING, "module": {"type": ["string", "null"], "maxLength": 128}}),
        "output_schema": obj({"items": {"type": "array", "maxItems": 200, "items": SELF_ANNOTATION}}, ("items",)),
    },
    ("PUT", "/api/self_ann/{dynamic}"): {
        "id": "base.self_annotation.change.apply",
        "schema": obj({"item_gid": STRING, "expected_revision": {"type": "integer", "minimum": 1}, "status": {"type": "string", "minLength": 1, "maxLength": 64}, "schedule": OPT_STRING, "note": TEXT, "attachments": {"type": "array", "maxItems": 100, "items": ANNOTATION_ATTACHMENT}, "idempotency_key": STRING}, ("item_gid", "expected_revision", "status", "schedule", "note", "attachments", "idempotency_key")),
        "output_schema": obj({"annotation": SELF_ANNOTATION}, ("annotation",)),
    },
    ("GET", "/api/users/me"): {
        "id": "base.identity.session.profile.get",
        "schema": obj({}),
        "output_schema": obj({"profile": IDENTITY_PROFILE}, ("profile",)),
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
    "base.plugin.installation.request.create": {"plugin_id": "plugin.example", "release_version": "1.2.3", "release_sha256": "sha256:" + "b" * 64, "requested_grants": ["project.read"], "idempotency_key": "idem-plugin-1"},
    "base.plugin.installation.transition.uninstall": {"plugin_id": "plugin.example", "expected_revision": 3, "retain_tenant_data": True, "idempotency_key": "idem-plugin-2"},
    "base.saved_view.search": {"module": "", "list_gid": None},
    "base.saved_view.create": {"name": "Open", "config": {"columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}], "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}], "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}], "groupBy": None, "viewType": "grid", "treeParentField": None}, "share_scope": "private", "idempotency_key": "idem-1"},
    "base.saved_view.update": {"view_gid": "view_1", "expected_revision": 1, "name": "Open", "config": {"columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}], "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}], "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}], "groupBy": None, "viewType": "grid", "treeParentField": None}, "idempotency_key": "idem-2"},
    "base.saved_view.copy": {"view_gid": "view_1", "name": "Copy", "idempotency_key": "idem-3"},
    "base.saved_view.delete": {"view_gid": "view_1", "expected_revision": 1, "idempotency_key": "idem-4"},
    "base.organization.team.directory.list": {},
    "base.team.directory.list": {},
    "base.self_annotation.batch.get": {"item_gids": ["item_1"]},
    "base.self_annotation.record.get": {"item_gid": "item_1"},
    "base.self_annotation.search": {"limit": 200, "status": None, "module": None},
    "base.self_annotation.change.apply": {"item_gid": "item_1", "expected_revision": 1, "status": "open", "schedule": "2026-08-28", "note": "note", "attachments": [{"attachment_gid": "att_1", "media_type": "image/png", "display_name": "photo.png", "size": 42, "checksum": "sha256:" + "a" * 64}], "idempotency_key": "idem-ann-1"},
    "base.identity.session.profile.get": {},
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
    "base.plugin.installation.request.create": {"installation": {"plugin_id": "plugin.example", "release_version": "1.2.3", "state": "disabled", "revision": 1, "granted_capabilities": ["project.read"], "tenant_gid": "tenant_1"}},
    "base.plugin.installation.transition.uninstall": {"installation": {"plugin_id": "plugin.example", "release_version": "1.2.3", "state": "uninstalled", "revision": 4, "granted_capabilities": [], "tenant_gid": "tenant_1"}},
    "base.saved_view.search": {"views": []},
    "base.saved_view.create": {"view": {"gid": "view_1", "name": "Open", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}], "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}], "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}], "groupBy": None, "viewType": "grid", "treeParentField": None}, "revision": 1, "deleted": False, "share_scope": "private", "grants": [], "restore": None}},
    "base.saved_view.update": {"view": {"gid": "view_1", "name": "Open", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}], "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}], "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}], "groupBy": None, "viewType": "grid", "treeParentField": None}, "revision": 2, "deleted": False, "share_scope": "private", "grants": [], "restore": None}},
    "base.saved_view.copy": {"view": {"gid": "view_2", "name": "Copy", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}], "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}], "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}], "groupBy": None, "viewType": "grid", "treeParentField": None}, "revision": 1, "deleted": False, "share_scope": "private", "grants": [], "restore": None}},
    "base.saved_view.delete": {"view": {"gid": "view_1", "name": "Open", "module": "", "list_gid": None, "owner_gid": "user_1", "config": {"columns": [{"key": "field_1", "visible": True, "order": 0, "width": 120}], "filters": [{"id": "filter_1", "field": "field_1", "op": "eq", "value": "open"}], "filterMode": "and", "sorts": [{"field": "field_1", "dir": "asc"}], "groupBy": None, "viewType": "grid", "treeParentField": None}, "revision": 2, "deleted": True, "share_scope": "private", "grants": [], "restore": {"available": True, "deleted_by": "user_1", "deleted_at": "transaction"}}},
    "base.organization.team.directory.list": {"teams": []},
    "base.team.directory.list": {"success": True, "data": []},
    "base.self_annotation.batch.get": {"items": []},
    "base.self_annotation.record.get": {"annotation": {"item_gid": "item_1", "status": "", "schedule": None, "note": "", "attachments": [], "revision": 1, "deleted": False, "restore": None}},
    "base.self_annotation.search": {"items": []},
    "base.self_annotation.change.apply": {"annotation": {"item_gid": "item_1", "status": "open", "schedule": "2026-08-28", "note": "note", "attachments": [{"attachment_gid": "att_1", "media_type": "image/png", "display_name": "photo.png", "size": 42, "checksum": "sha256:" + "a" * 64}], "revision": 2, "deleted": False, "restore": None}},
    "base.identity.session.profile.get": {"profile": {"actor_gid": "user_1", "display_name": "", "tenant_gid": "", "team_gids": [], "locale": "", "timezone": "", "permission_ids": []}},
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
