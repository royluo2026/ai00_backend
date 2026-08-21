"""Frozen Project Management outcomes backed by the application port."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec
from backend.platform_sdk.access import build_access_scope

from ..application.outcomes import project_outcome_port
from ..application.service import SUPPORTED_OPERATIONS
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


__all__ = [
    "OPERATION_INPUT_SCHEMA",
    "PROJECT_CAPABILITY_IDS",
    "register_reviewed_capabilities",
]
