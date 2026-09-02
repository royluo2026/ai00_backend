"""Frozen Project Management outcomes backed by the application port."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec
from backend.platform_sdk.access import build_access_scope

from ..application.outcomes import project_outcome_port
from ..application.service import (
    APPROVAL_REJECT_CAPABILITY_ID,
    APPROVAL_REJECT_CAPABILITY_VERSION,
    SUPPORTED_OPERATIONS,
)
from .provider import DEPRECATED_CAPABILITY_IDS, register_capability


PROJECT_CAPABILITY_IDS = frozenset(
    {
        "project.activity.aggregate",
        "project.approval.change.apply",
        "project.approval.read",
        "project.bitable_binding.change.apply",
        "project.bitable_binding.read",
        "project.change_log.read",
        "project.collaboration.change.apply",
        "project.collaboration.read",
        "project.craft_scope.read",
        "project.follow.change.apply",
        "project.follow.read",
        "project.issue.change.apply",
        "project.issue.read",
        "project.list.change.apply",
        "project.list.read",
        "project.member.change.apply",
        "project.member.read",
        "project.notification.change.apply",
        "project.notification.read",
        "project.permission_request.change.apply",
        "project.permission_request.read",
        "project.project.change.apply",
        "project.project.read",
        "project.sharing.change.apply",
        "project.sharing.read",
        "project.task.change.apply",
        "project.task.read",
        "project.task_template.change.apply",
        "project.task_template.read",
        "project.workbench.change.apply",
        "project.workbench.read",
    }
)

EXACT_CAPABILITY_IDS = frozenset({APPROVAL_REJECT_CAPABILITY_ID})

_ARGUMENT_FIELDS = {
    name: {"description": "Operation-specific value validated by the Project application layer."}
    for name in (
        "assignee_map", "assignee_role", "body", "brand", "color", "comment",
        "content", "current_scope", "data", "dep_condition", "dep_group", "description",
        "display_name", "due_offset_days", "edge_type", "entries", "expires_at",
        "factory_gid", "gid", "include_archived", "include_deleted", "item_gid",
        "item_title", "item_type", "jph", "key", "label", "list_gid",
        "local_gid", "message", "model_year", "name", "new_list_gid",
        "notify_on", "order_type", "owner_gid", "owner_team_gid", "owner_type",
        "owner_user_gid", "permission", "platform", "priority", "project_code", "project_gid", "user_gid", "member_gid", "project_role",
        "q", "read_scope", "recipient_gid", "reviewer_gid", "scope",
        "section_gid", "share_scope", "shared_to", "sort_order", "source_gid",
        "source_ref", "start_date", "status", "storage_scope", "suffix",
        "target_gid", "target_scope", "target_type", "team_id", "template_gid",
        "title", "title_pattern", "title_vars", "token", "type", "unread_only",
        "updates", "vehicle_model_gid", "vehicle_type", "visibility", "want_permission",
        "widgets", "write_scope",
    )
}


def _object(properties: dict[str, Any], *, required: tuple[str, ...] = ()) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object", "properties": properties, "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


_TEXT = {"type": "string"}
_NULLABLE_TEXT = {"type": ["string", "null"]}
_STRING_LIST = {"type": "array", "items": _TEXT, "maxItems": 200}
_SCOPE = _object({
    "user_gid": _TEXT,
    "team_gids": _STRING_LIST,
    "team_member_gids": _STRING_LIST,
    "project_gids": _STRING_LIST,
    "is_admin": {"type": "boolean"},
}, required=("user_gid",))

_ATOMIC_ARGUMENT_SCHEMAS: dict[str, dict[str, Any]] = {
    "projects.search": _object({
        "include_deleted": {"type": "boolean"},
        "include_archived": {"type": "boolean"},
        "scope": _SCOPE,
    }),
    "tasks.search": _object({
        "project_gid": _NULLABLE_TEXT,
        "status": _NULLABLE_TEXT,
        "list_gid": _NULLABLE_TEXT,
        "scheduled_date_from": _NULLABLE_TEXT,
        "q": _NULLABLE_TEXT,
        "page_size": {"type": "integer", "minimum": 1, "maximum": 500},
        "scope": _SCOPE,
    }),
    "issues.search": _object({
        "project_gid": _NULLABLE_TEXT,
        "status": _NULLABLE_TEXT,
        "list_gid": _NULLABLE_TEXT,
        "q": _NULLABLE_TEXT,
        "page_size": {"type": "integer", "minimum": 1, "maximum": 500},
        "scope": _SCOPE,
    }),
    "lists.search": _object({
        "item_type": _NULLABLE_TEXT,
        "owner_team_gid": _NULLABLE_TEXT,
        "q": _NULLABLE_TEXT,
        "scope": _SCOPE,
    }),
    "follows.list": _object({"item_type": _NULLABLE_TEXT}),
    "notifications.unread_count": _object({}),
}

_PROJECT = _object({
    "gid": _TEXT, "name": _TEXT, "project_code": _TEXT,
    "model_year": {"type": ["integer", "null"]}, "suffix": _TEXT,
    "description": _TEXT, "status": _TEXT,
    "vehicle_model_gid": _NULLABLE_TEXT, "factory_gid": _NULLABLE_TEXT,
    "team_id": _NULLABLE_TEXT, "owner_gid": _NULLABLE_TEXT,
    "owner_name": _TEXT, "share_scope": _TEXT,
    "jph": {"type": ["integer", "number", "null"]},
    "is_deleted": {"type": "boolean"}, "is_archived": {"type": "boolean"},
    "deleted_at": _NULLABLE_TEXT, "archived_at": _NULLABLE_TEXT,
    "created_at": _TEXT, "updated_at": _TEXT,
})

_WORK_ITEM = _object({
    name: schema for name, schema in {
        **{name: _NULLABLE_TEXT for name in (
            "gid", "display_id", "title", "description", "owner_gid", "owner_user_gid",
            "assignee_team_gid", "project_gid", "status", "share_scope", "list_gid",
            "priority", "review_date", "meeting_level", "meeting_doc_link", "due_date",
            "plan_start", "plan_end", "actual_start", "actual_end", "scheduled_date",
            "scheduled_start_time", "parent_task_gid", "node_type", "canvas_icon",
            "canvas_row_gid", "canvas_col_gid",
            "feishu_assignee_open_id", "feishu_assignee_name", "feishu_group_chat_id",
            "feishu_group_name", "severity", "occurrence_root_cause", "escape_root_cause",
            "interim_action", "permanent_action", "related_task_gid", "related_knowledge_gid",
            "approval_order_gid", "bop_entry_gid", "owner_name", "created_at", "updated_at",
            "deleted_at",
        )},
        "source_ref": _object({}),
        "attachments": {"type": "array", "items": {}, "maxItems": 200},
        "progress_logs": {"type": "array", "items": {}, "maxItems": 200},
        "tracking_refs": {"type": "array", "items": {}, "maxItems": 200},
        "feishu_groups": {"type": "array", "items": {}, "maxItems": 200},
        "feishu_docs": {"type": "array", "items": {}, "maxItems": 200},
        "is_deleted": {"type": "boolean"},
        "completion": {"type": ["integer", "number", "null"]},
        "time_estimate": {"type": ["integer", "null"]},
        "canvas_x": {"type": ["integer", "number", "null"]},
        "canvas_y": {"type": ["integer", "number", "null"]},
    }.items()
})

_PROJECT_LIST = _object({
    "gid": _TEXT, "name": _TEXT, "color": _TEXT, "storage_scope": _TEXT,
    "owner_type": _TEXT, "owner_gid": _TEXT, "creator_gid": _TEXT,
    "visibility": _TEXT, "read_scope": _TEXT, "write_scope": _TEXT,
    "deleted_at": _NULLABLE_TEXT, "item_type": _TEXT,
    "sort_order": {"type": "integer"}, "created_at": _TEXT,
    "project_gid": _NULLABLE_TEXT,
})

_FOLLOW = _object({
    "gid": _TEXT, "item_type": _TEXT, "item_gid": _TEXT,
    "item_title": _TEXT, "notify_on": _STRING_LIST, "created_at": _TEXT,
})

_VEHICLE_MODEL = _object({
    "gid": _TEXT, "name": _TEXT, "brand": _TEXT, "platform": _TEXT,
    "vehicle_type": _TEXT, "created_at": _TEXT,
})


def _application_result(data_schema: dict[str, Any]) -> dict[str, Any]:
    return _object(
        {"success": {"type": "boolean"}, "data": data_schema},
        required=("success", "data"),
    )


_ATOMIC_OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "projects.search": _application_result({"type": "array", "items": _PROJECT, "maxItems": 500}),
    "tasks.search": _application_result({"type": "array", "items": _WORK_ITEM, "maxItems": 500}),
    "issues.search": _application_result({"type": "array", "items": _WORK_ITEM, "maxItems": 500}),
    "lists.search": _application_result({"type": "array", "items": _PROJECT_LIST, "maxItems": 500}),
    "follows.list": _application_result({"type": "array", "items": _FOLLOW, "maxItems": 500}),
    "notifications.unread_count": _application_result(
        _object({"count": {"type": "integer", "minimum": 0}}, required=("count",))
    ),
    "vehicle_models.list": _application_result(
        {"type": "array", "items": _VEHICLE_MODEL, "maxItems": 500}
    ),
}


def _operation_schema(capability_id: str) -> dict[str, Any]:
    operations = SUPPORTED_OPERATIONS.get(capability_id, frozenset())
    if not operations:
        raise ValueError(f"missing Project operation contract: {capability_id}")
    return {
        "type": "object",
        "required": ["operation", "arguments"],
        "properties": {
            "operation": {
                "type": "string", "enum": sorted(operations),
                "minLength": 1, "maxLength": 128,
            },
            "arguments": {
                "type": "object", "properties": _ARGUMENT_FIELDS,
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _disabled_operation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["operation", "arguments"],
        "properties": {
            "operation": {"type": "string", "enum": []},
            "arguments": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        "additionalProperties": False,
    }


OPERATION_INPUT_SCHEMA = {
    "type": "object",
    "required": ["operation", "arguments"],
    "properties": {
        "operation": {"type": "string", "minLength": 1, "maxLength": 128},
        # Each operation validates its own bounded argument contract in the
        # Project application layer; the outer Gateway envelope stays closed.
        "arguments": {
            "description": "Operation-specific object validated by the Project application layer."
        },
    },
}


def _handler(capability_id: str):
    def invoke(payload: dict[str, Any], context: object) -> dict[str, Any]:
        # Access scope is server-derived for browser capability invocations.
        # Callers may not forge team/project membership through the capability
        # payload; the legacy REST adapter already supplied this projection.
        if capability_id == "project.project.read" and payload.get("operation") == "projects.search":
            arguments = payload.get("arguments")
            if isinstance(arguments, dict) and "scope" not in arguments:
                actor_gid = str(getattr(context, "user_gid", "") or "")
                active_roles = set(getattr(context, "active_roles", ()) or ())
                user = {
                    "gid": actor_gid,
                    "team_id": getattr(context, "team_gid", None),
                    "org_role": next((role for role in ("super_admin", "team_admin") if role in active_roles), "member"),
                }
                payload = {**payload, "arguments": {**arguments, "scope": build_access_scope(user)}}
        return {"data": project_outcome_port.invoke(capability_id, payload, context)}

    return invoke


_SERVER_SCOPED_READS = {
    ("project.project.read", "projects.search"),
    ("project.list.read", "lists.search"),
    ("project.task.read", "tasks.search"),
    ("project.issue.read", "issues.search"),
}


def _atomic_handler(capability_id: str, operation: str):
    def invoke(payload: dict[str, Any], context: object) -> dict[str, Any]:
        arguments = dict(payload.get("arguments", payload) if isinstance(payload, dict) else {})
        if (capability_id, operation) in _SERVER_SCOPED_READS:
            roles = set(getattr(context, "active_roles", ()) or ())
            user = {
                "gid": str(getattr(context, "user_gid", "") or ""),
                "team_id": getattr(context, "team_gid", None),
                "org_role": next((role for role in ("super_admin", "team_admin") if role in roles), "member"),
            }
            arguments["scope"] = build_access_scope(user)
        return {"data": project_outcome_port.invoke(
            capability_id, {"operation": operation, "arguments": arguments}, context,
        )}

    return invoke


def _approval_reject_handler(payload: dict[str, Any], context: object) -> dict[str, Any]:
    return project_outcome_port.invoke(APPROVAL_REJECT_CAPABILITY_ID, payload, context)


def register_reviewed_capabilities(registry: Any) -> None:
    for capability_id in sorted(PROJECT_CAPABILITY_IDS):
        is_write = capability_id.endswith(".change.apply")
        register_capability(
            registry,
            CapabilitySpec(
                id=capability_id,
                owner="project_management",
                description=f"Execute the reviewed {capability_id} project outcome.",
                use_when="A governed consumer needs this Project Management outcome.",
                do_not_use_when="The operation belongs to another domain.",
                risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                confirmation="user" if is_write else "none",
                permissions=("project.manage_any",) if is_write else ("project.view",),
                input_schema=(
                    _disabled_operation_schema()
                    if capability_id in DEPRECATED_CAPABILITY_IDS
                    else (
                        _operation_schema(capability_id)
                        if capability_id in SUPPORTED_OPERATIONS
                        else OPERATION_INPUT_SCHEMA
                    )
                ),
                output_schema={
                    "type": "object",
                    "required": ["data"],
                    "properties": {
                        "data": {
                            "description": "Operation-specific result validated by the Project application layer."
                        }
                    },
                },
                tags=("project_management", "write" if is_write else "read"),
            ),
            _handler(capability_id),
        )

    # Freeze each supported operation as its own Capability.  The historical
    # operation envelope stays as a compatibility facade for migration only.
    for capability_id in sorted(PROJECT_CAPABILITY_IDS - DEPRECATED_CAPABILITY_IDS):
        operations = sorted(SUPPORTED_OPERATIONS.get(capability_id, ()))
        if not operations:
            continue
        for operation in operations:
            atomic_id = f"{capability_id}.atomic.{operation.replace('.', '_')}"
            is_write = capability_id.endswith(".change.apply")
            register_capability(
                registry,
                CapabilitySpec(
                    id=atomic_id, owner="project_management",
                    description=f"Execute Project Management operation {operation}.",
                    use_when="A governed consumer needs exactly this Project Management operation.",
                    do_not_use_when="The request selects another operation or domain.",
                    risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                    confirmation="user" if is_write else "none",
                    permissions=("project.manage_any",) if is_write else ("project.view",),
                    input_schema=_object({
                        "arguments": _ATOMIC_ARGUMENT_SCHEMAS.get(
                            operation, _object(_ARGUMENT_FIELDS)
                        ),
                    }, required=("arguments",)),
                    output_schema=_object({
                        "data": _ATOMIC_OUTPUT_SCHEMAS.get(operation, _object({})),
                    }, required=("data",)),
                    tags=("project_management", "atomic", operation),
                ),
                _atomic_handler(capability_id, operation),
            )

    register_capability(
        registry,
        CapabilitySpec(
            id=APPROVAL_REJECT_CAPABILITY_ID,
            version=APPROVAL_REJECT_CAPABILITY_VERSION,
            owner="project_management",
            description="Reject one Project approval order and durably enqueue its notification.",
            use_when="A confirmed reviewer rejects an in-review Project approval order.",
            do_not_use_when="The caller needs another approval transition or a Craft-owned outcome.",
            risk=CapabilityRisk.WRITE,
            confirmation="user",
            idempotent=True,
            permissions=("project.manage_any",),
            input_schema={
                "type": "object",
                "required": ["order_gid", "comment", "expected_revision"],
                "properties": {
                    "order_gid": {"type": "string", "minLength": 1, "maxLength": 128},
                    "comment": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "expected_revision": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["order_gid", "status", "revision", "notification_event_gid"],
                "properties": {
                    "order_gid": {"type": "string"},
                    "status": {"type": "string", "enum": ["rejected"]},
                    "revision": {"type": "integer", "minimum": 1},
                    "notification_event_gid": {"type": "string"},
                },
                "additionalProperties": False,
            },
            tags=("project_management", "approval", "reject", "write"),
        ),
        _approval_reject_handler,
    )


__all__ = [
    "EXACT_CAPABILITY_IDS",
    "OPERATION_INPUT_SCHEMA",
    "PROJECT_CAPABILITY_IDS",
    "register_reviewed_capabilities",
]
