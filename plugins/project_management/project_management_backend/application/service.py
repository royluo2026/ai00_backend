"""Project Management application service and operation dispatch."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
from typing import Any, Protocol
from uuid import uuid4
import secrets
import re
import json
from datetime import date, timedelta

from backend.capability_v2.provider_contracts import CapabilityBusinessError


APPROVAL_REJECT_CAPABILITY_ID = "project.approval.order.reject"
APPROVAL_REJECT_CAPABILITY_VERSION = 1
_REJECTION_RESULT_KEYS = frozenset({"order_gid", "status", "revision", "notification_event_gid"})


def canonical_rejection_result(result: Mapping[str, Any]) -> str:
    """Encode the exact rejection response with stable UTF-8 JSON semantics."""
    if set(result) != _REJECTION_RESULT_KEYS:
        raise CapabilityBusinessError("invalid_result", "approval rejection result is not closed")
    return json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rejection_result_from_canonical(serialized: str) -> dict[str, Any]:
    try:
        result = json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise CapabilityBusinessError("invalid_result", "stored approval rejection result is invalid") from exc
    if not isinstance(result, dict) or set(result) != _REJECTION_RESULT_KEYS:
        raise CapabilityBusinessError("invalid_result", "stored approval rejection result is not closed")
    return result


@dataclass(frozen=True)
class RejectOrder:
    order_gid: str
    comment: str
    expected_revision: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RejectOrder":
        if set(payload) != {"order_gid", "comment", "expected_revision"}:
            raise CapabilityBusinessError("invalid_input", "reject order input is closed")
        order_gid = _required_text(payload, "order_gid")
        comment = _required_text(payload, "comment")
        expected_revision = payload["expected_revision"]
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise CapabilityBusinessError("invalid_input", "expected_revision must be a positive integer")
        return cls(order_gid=order_gid, comment=comment, expected_revision=expected_revision)

    def payload_hash(self) -> str:
        encoded = json.dumps(
            {"order_gid": self.order_gid, "comment": self.comment, "expected_revision": self.expected_revision},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ItemEntryRepository(Protocol):
    def list_item_entries(self, item_type: str, item_gid: str) -> list[dict[str, Any]]: ...
    def replace_item_entries(
        self, item_type: str, item_gid: str, entries: list[dict[str, Any]]
    ) -> None: ...
    def delete_item_entries(self, item_type: str, item_gid: str) -> None: ...
    def get_list_owner(self, list_gid: str) -> str | None: ...
    def get_item_list_owner(self, item_type: str, item_gid: str) -> str | None: ...
    def list_change_logs_by_list(
        self, list_gid: str, limit: int, offset: int
    ) -> list[dict[str, Any]]: ...
    def list_change_logs_by_item(
        self,
        item_type: str,
        item_gid: str,
        changed_by: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...
    def list_collaboration_sessions(
        self, section_gid: str | None
    ) -> list[dict[str, Any]]: ...
    def get_collaboration_session(self, gid: str) -> dict[str, Any] | None: ...
    def create_collaboration_session(
        self, gid: str, section_gid: str, owner_gid: str
    ) -> None: ...
    def join_collaboration_session(self, gid: str, participant_gid: str) -> None: ...
    def end_collaboration_session(self, gid: str, owner_gid: str) -> bool: ...
    def create_share_link(self, token: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def resolve_share_link(self, token: str) -> dict[str, Any] | None: ...
    def get_list_access(self, list_gid: str, user_gid: str, team_gid: str | None) -> str: ...
    def delete_share_link(self, token: str, user_gid: str, is_super: bool) -> str: ...
    def create_permission_request(self, gid: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def list_permission_requests(self, target_gid: str | None, status_filter: str | None) -> list[dict[str, Any]]: ...
    def decide_permission_request(self, gid: str, responder_gid: str, decision: str) -> tuple[str, dict[str, Any] | None]: ...
    def is_list_owner(self, list_gid: str, user_gid: str) -> bool: ...
    def list_list_shares(self, list_gid: str) -> list[dict[str, Any]]: ...
    def upsert_list_share(self, gid: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def delete_list_share(self, list_gid: str, gid: str) -> None: ...
    def upsert_item_share(self, gid: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def delete_item_share(self, gid: str, user_gid: str) -> str: ...
    def search_lists(self, filters: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]: ...
    def create_list(self, gid: str, values: dict[str, Any]) -> None: ...
    def get_list(self, gid: str) -> dict[str, Any] | None: ...
    def update_list(self, gid: str, updates: dict[str, Any]) -> bool: ...
    def archive_list(self, gid: str) -> bool: ...
    def retarget_list_items(self, gid: str, new_list_gid: str, item_type: str) -> bool: ...
    def search_projects(self, filters: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]: ...
    def create_project(self, gid: str, values: dict[str, Any]) -> None: ...
    def get_project(self, gid: str) -> dict[str, Any] | None: ...
    def update_project(self, gid: str, updates: dict[str, Any]) -> bool: ...
    def delete_project(self, gid: str) -> bool: ...
    def list_vehicle_models(self) -> list[dict[str, Any]]: ...
    def create_vehicle_model(self, gid: str, values: dict[str, Any]) -> None: ...
    def update_vehicle_model(self, gid: str, values: dict[str, Any]) -> bool: ...
    def delete_vehicle_model(self, gid: str) -> bool: ...
    def list_task_templates(self) -> list[dict[str, Any]]: ...
    def create_task_template(self, gid: str, values: dict[str, Any]) -> None: ...
    def get_task_template(self, gid: str) -> dict[str, Any] | None: ...
    def update_task_template(self, gid: str, updates: dict[str, Any]) -> bool: ...
    def delete_task_template(self, gid: str) -> bool: ...
    def create_task_template_item(self, gid: str, values: dict[str, Any]) -> None: ...
    def update_task_template_item(self, gid: str, updates: dict[str, Any]) -> bool: ...
    def delete_task_template_item(self, gid: str) -> bool: ...
    def create_tasks_from_template(self, tasks: list[dict[str, Any]]) -> None: ...
    def search_approval_orders(self, filters: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]: ...
    def create_approval_order(self, gid: str, values: dict[str, Any]) -> None: ...
    def get_approval_order(self, gid: str) -> dict[str, Any] | None: ...
    def transition_approval_order(self, gid: str, action: str, actor_gid: str, comment: str) -> dict[str, Any] | None: ...
    def transaction(self): ...
    def apply_scope_upgrade(self, item_type: str, item_gid: str, target_scope: str) -> bool: ...
    def list_workbenches(self, user_gid: str, team_gid: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[Any, Any]]: ...
    def count_workbenches(self, owner_type: str, owner_gid: str) -> int: ...
    def create_workbench(self, gid: str, values: dict[str, Any]) -> None: ...
    def get_workbench(self, gid: str) -> dict[str, Any] | None: ...
    def update_workbench(self, gid: str, updates: dict[str, Any]) -> bool: ...
    def delete_workbench(self, gid: str) -> bool: ...
    def get_workbench_override(self, gid: str, user_gid: str) -> dict[str, Any] | None: ...
    def upsert_workbench_override(self, gid: str, user_gid: str, widgets: list[Any]) -> None: ...
    def delete_workbench_override(self, gid: str, user_gid: str) -> None: ...
    def list_follows(self, user_gid: str, item_type: str | None) -> list[dict[str, Any]]: ...
    def get_follow(self, user_gid: str, item_type: str, item_gid: str) -> dict[str, Any] | None: ...
    def create_follow(self, gid: str, values: dict[str, Any]) -> bool: ...
    def update_follow(self, gid: str, user_gid: str, notify_on: list[str]) -> bool: ...
    def delete_follow(self, gid: str, user_gid: str) -> bool: ...
    def create_notification(self, gid: str, values: dict[str, Any]) -> None: ...
    def list_notifications(self, user_gid: str, unread_only: bool) -> list[dict[str, Any]]: ...
    def count_unread_notifications(self, user_gid: str) -> int: ...
    def mark_notification_read(self, gid: str, user_gid: str) -> bool: ...
    def mark_all_notifications_read(self, user_gid: str) -> None: ...
    def search_work_items(self, item_type: str, filters: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]: ...
    def create_work_item(self, item_type: str, gid: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def get_work_item(self, item_type: str, gid: str) -> dict[str, Any] | None: ...
    def update_work_item(self, item_type: str, gid: str, updates: dict[str, Any], actor_gid: str, events: list[str]) -> bool: ...
    def delete_work_item(self, item_type: str, gid: str, user_gid: str) -> bool: ...
    def list_task_dependencies(self, list_gid: str) -> list[dict[str, Any]]: ...
    def create_task_dependency(self, gid: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def update_task_dependency(self, gid: str, updates: dict[str, Any]) -> bool: ...
    def delete_task_dependency(self, gid: str) -> bool: ...
    def get_annotation(self, key: str) -> Any: ...
    def put_annotation(self, key: str, data: Any) -> None: ...


_OPERATIONS = {
    "project.change_log.read": frozenset({"change_logs.search"}),
    "project.collaboration.read": frozenset(
        {"collaboration.sessions.list", "collaboration.sessions.get"}
    ),
    "project.collaboration.change.apply": frozenset(
        {
            "collaboration.sessions.create",
            "collaboration.sessions.join",
            "collaboration.sessions.end",
        }
    ),
    "project.list.read": frozenset({"item_entries.get", "lists.search"}),
    "project.list.change.apply": frozenset(
        {"item_entries.replace", "item_entries.delete", "lists.create", "lists.update", "lists.delete", "lists.retarget"}
    ),
    "project.sharing.read": frozenset({"share_links.resolve", "shares.list.list"}),
    "project.sharing.change.apply": frozenset(
        {"share_links.create", "share_links.delete", "shares.list.create", "shares.list.delete", "shares.item.create", "shares.item.delete"}
    ),
    "project.permission_request.read": frozenset({"permission_requests.list"}),
    "project.permission_request.change.apply": frozenset(
        {"permission_requests.create", "permission_requests.approve", "permission_requests.reject"}
    ),
    "project.project.read": frozenset({"projects.search", "projects.get", "vehicle_models.list"}),
    "project.project.change.apply": frozenset({"projects.create", "projects.update", "projects.delete", "vehicle_models.create", "vehicle_models.update", "vehicle_models.delete"}),
    "project.member.read": frozenset({"members.list"}),
    "project.member.change.apply": frozenset({"members.add", "members.remove", "members.line_assignment.replace"}),
    "project.task_template.read": frozenset({"task_templates.list", "task_templates.get"}),
    "project.task_template.change.apply": frozenset({"task_templates.create", "task_templates.update", "task_templates.delete", "task_templates.items.create", "task_templates.items.update", "task_templates.items.delete", "task_templates.instantiate"}),
    "project.approval.read": frozenset({"approval.orders.search", "approval.orders.get"}),
    "project.approval.change.apply": frozenset({"approval.orders.create", "approval.orders.start", "approval.orders.approve", "approval.orders.reject", "approval.orders.withdraw", "approval.scope_upgrade.create"}),
    "project.workbench.read": frozenset({"workbenches.list", "workbenches.overrides.get", "annotations.get"}),
    "project.workbench.change.apply": frozenset({"workbenches.create", "workbenches.update", "workbenches.delete", "workbenches.overrides.upsert", "workbenches.overrides.delete", "annotations.put"}),
    "project.follow.read": frozenset({"follows.list", "follows.check"}),
    "project.follow.change.apply": frozenset({"follows.create", "follows.update", "follows.delete"}),
    "project.notification.read": frozenset({"notifications.list", "notifications.unread_count"}),
    "project.notification.change.apply": frozenset({"notifications.create", "notifications.mark_read", "notifications.mark_all_read"}),
    "project.task.read": frozenset({"tasks.search", "tasks.get", "task_dependencies.list"}),
    "project.task.change.apply": frozenset({"tasks.create", "tasks.promote", "tasks.update", "tasks.delete", "task_dependencies.create", "task_dependencies.update", "task_dependencies.delete"}),
    "project.issue.read": frozenset({"issues.search", "issues.get"}),
    "project.issue.change.apply": frozenset({"issues.create", "issues.promote", "issues.update", "issues.delete"}),
}

# Public read-only projection used by the descriptor builder.  Keeping the
# dispatch table in the application layer prevents the schema from becoming a
# second hand-maintained operation list.
SUPPORTED_OPERATIONS = _OPERATIONS


def _required_text(arguments: Mapping[str, Any], name: str) -> str:
    value = str(arguments.get(name) or "").strip()
    if not value:
        raise CapabilityBusinessError("invalid_input", f"{name} is required")
    return value


def _bounded_int(
    arguments: Mapping[str, Any], name: str, *, default: int, minimum: int, maximum: int
) -> int:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CapabilityBusinessError("invalid_input", f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise CapabilityBusinessError(
            "invalid_input", f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _entry(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "gid": row.get("gid", ""),
        "parent_id": row.get("parent_id"),
        "section": row.get("section", "detail"),
        "author": row.get("author", "human"),
        "author_name": row.get("author_name", ""),
        "author_gid": row.get("author_gid", ""),
        "content": row.get("content", ""),
        "resolved": bool(row.get("resolved", False)),
        "sort_order": float(row.get("sort_order", 0)),
        "read_by_human": bool(row.get("read_by_human", True)),
        "ai_status": row.get("ai_status", "unread"),
        "created_at": row.get("created_at", 0),
    }


def _collaboration_session(
    row: Mapping[str, Any], *, include_meta: bool = False
) -> dict[str, Any]:
    result = {
        "gid": row["gid"],
        "section_gid": row["section_gid"],
        "owner_gid": row["owner_gid"],
        "status": row["status"],
        "participants": row["participants"],
        "created_at": str(row["created_at"]),
        "ended_at": str(row["ended_at"]) if row.get("ended_at") else None,
    }
    if include_meta:
        result["meta"] = row.get("meta")
    return result


def _visibility_to_read_scope(visibility: str) -> str:
    return {"public": "global", "private": "personal", "team": "team", "project": "project"}.get(visibility, "team")


def _visibility_to_write_scope(visibility: str) -> str:
    return {"public": "team", "private": "personal", "team": "team", "project": "team"}.get(visibility, "personal")


def _project_list(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gid": row["gid"], "name": row["name"], "color": row["color"],
        "storage_scope": row["storage_scope"], "owner_type": row["owner_type"],
        "owner_gid": row["owner_gid"], "creator_gid": row.get("creator_gid") or "",
        "visibility": row.get("visibility") or "team",
        "read_scope": row.get("read_scope") or row.get("visibility") or "team",
        "write_scope": row.get("write_scope") or "personal",
        "deleted_at": str(row["deleted_at"]) if row.get("deleted_at") else None,
        "item_type": row.get("item_type") or "task", "sort_order": row["sort_order"],
        "created_at": str(row["created_at"]), "project_gid": row.get("project_gid") or None,
    }


def _project_name(project_code: str, model_year: Any, suffix: str) -> str:
    return "-".join(str(value) for value in (project_code, model_year, suffix) if value) or project_code


def _project(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gid": row["gid"], "name": row["name"], "project_code": row.get("project_code") or "",
        "model_year": row.get("model_year"), "suffix": row.get("suffix") or "",
        "description": row.get("description") or "", "status": row["status"],
        "vehicle_model_gid": row.get("vehicle_model_gid"), "factory_gid": row.get("factory_gid"),
        "team_id": row.get("team_id"), "owner_gid": row.get("owner_gid"),
        "owner_name": row.get("owner_name") or "", "share_scope": row.get("share_scope") or "team",
        "jph": row.get("jph"), "is_deleted": bool(row.get("is_deleted")),
        "is_archived": bool(row.get("is_archived")),
        "deleted_at": str(row["deleted_at"]) if row.get("deleted_at") else None,
        "archived_at": str(row["archived_at"]) if row.get("archived_at") else None,
        "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
    }


def _template_item_values(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title_pattern": _required_text(arguments, "title_pattern"),
        "description": str(arguments.get("description") or ""),
        "priority": str(arguments.get("priority") or "normal"),
        "assignee_role": arguments.get("assignee_role"),
        "due_offset_days": arguments.get("due_offset_days"),
        "share_scope": str(arguments.get("share_scope") or "team"),
        "sort_order": int(arguments.get("sort_order") or 0),
    }


def _workbench(row: Mapping[str, Any], override: Mapping[str, Any] | list[Any] | None = None) -> dict[str, Any]:
    result = {"gid": row["gid"], "owner_type": row["owner_type"], "owner_gid": row["owner_gid"], "name": row["name"], "sort_order": row["sort_order"], "widgets": row["widgets"] if isinstance(row.get("widgets"), list) else [], "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"])}
    if override is not None: result["override"] = override.get("widgets", []) if isinstance(override, Mapping) else override
    return result


def _notify_conditions(raw: Any, valid: set[str]) -> list[str]:
    if isinstance(raw, list): return [str(value) for value in raw if str(value) in valid]
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw) if raw.strip().startswith("[") else None
            if isinstance(decoded, list): return [str(value) for value in decoded if str(value) in valid]
        except ValueError: pass
        aliases = {"all": ["any_change"], "any_change": ["any_change"], "key_changes": ["status_change", "resolved", "assigned_to_me"], "none": []}
        return aliases.get(raw, [raw] if raw in valid else [])
    return []


_TASK_UPDATE_FIELDS = {"title", "description", "status", "priority", "review_date", "meeting_level", "meeting_doc_link", "due_date", "plan_start", "plan_end", "actual_start", "actual_end", "share_scope", "assignee_team_gid", "project_gid", "attachments", "list_gid", "scheduled_date", "scheduled_start_time", "time_estimate", "is_deleted", "parent_task_gid", "canvas_x", "canvas_y", "completion", "node_type", "canvas_icon", "feishu_assignee_open_id", "feishu_assignee_name", "feishu_group_chat_id", "feishu_group_name", "feishu_groups", "feishu_docs"}
_ISSUE_UPDATE_FIELDS = {"title", "description", "severity", "status", "assignee_team_gid", "project_gid", "occurrence_root_cause", "escape_root_cause", "interim_action", "permanent_action", "related_task_gid", "related_knowledge_gid", "approval_order_gid", "bop_entry_gid", "share_scope", "attachments", "list_gid", "scheduled_date", "feishu_assignee_open_id", "feishu_assignee_name", "feishu_group_chat_id", "feishu_group_name", "feishu_groups", "feishu_docs"}


def _work_item_values(item_type: str, args: Mapping[str, Any], user_gid: str, display_id: str) -> dict[str, Any]:
    common = {"display_id": display_id, "title": _required_text(args, "title"), "description": str(args.get("description") or ""), "owner_gid": str(args.get("owner_gid") or ""), "owner_user_gid": user_gid, "assignee_team_gid": args.get("assignee_team_gid"), "project_gid": args.get("project_gid"), "status": str(args.get("status") or ("pending" if item_type == "task" else "open")), "share_scope": str(args.get("share_scope") or "project"), "list_gid": args.get("list_gid"), "attachments": list(args.get("attachments") or [])}
    if item_type == "task":
        common.update({key: args.get(key, default) for key, default in {"priority": "normal", "source_ref": {}, "review_date": None, "meeting_level": "none", "meeting_doc_link": None, "progress_logs": [], "due_date": None, "plan_start": None, "plan_end": None, "actual_start": None, "actual_end": None, "canvas_x": None, "canvas_y": None, "node_type": "normal", "canvas_icon": "star"}.items()})
    else:
        common.update({key: args.get(key, default) for key, default in {"severity": "low", "tracking_refs": [], "occurrence_root_cause": None, "escape_root_cause": None, "interim_action": None, "permanent_action": None, "source_ref": {}, "related_task_gid": None, "related_knowledge_gid": None, "approval_order_gid": None, "bop_entry_gid": None}.items()})
    return common


def _work_item_output(item_type: str, row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("source_ref",): result[key] = result.get(key) or {}
    for key in ("progress_logs", "tracking_refs", "attachments", "feishu_groups", "feishu_docs"): result[key] = result.get(key) or []
    result["created_at"] = str(result.get("created_at") or ""); result["updated_at"] = str(result.get("updated_at") or "")
    if item_type == "task":
        result.setdefault("owner_name", ""); result["is_deleted"] = bool(result.get("is_deleted", False)); result["completion"] = result.get("completion") or 0; result["node_type"] = result.get("node_type") or "normal"; result["canvas_icon"] = result.get("canvas_icon") or "star"
    return result


class ProjectManagementApplication:
    def __init__(
        self,
        repository: ItemEntryRepository,
        *,
        next_id: Callable[[], str] | None = None,
        next_token: Callable[[], str] | None = None,
        next_display_id: Callable[[str], int] | None = None,
    ) -> None:
        self._repository = repository
        self._next_id = next_id or (lambda: str(uuid4()))
        self._next_token = next_token or (lambda: secrets.token_urlsafe(16))
        if next_display_id is None:
            from backend.platform_sdk.ids import next_display_id as allocate_display_id
            next_display_id = allocate_display_id
        self._next_display_id = next_display_id

    def invoke(
        self,
        capability_id: str,
        payload: dict[str, Any],
        _context: object,
    ) -> Any:
        if capability_id == APPROVAL_REJECT_CAPABILITY_ID:
            if not isinstance(payload, Mapping):
                raise CapabilityBusinessError("invalid_input", "payload must be an object")
            return self.reject_order(RejectOrder.from_payload(payload), _context)
        operation = str(payload.get("operation") or "")
        if operation not in _OPERATIONS.get(capability_id, frozenset()):
            raise CapabilityBusinessError(
                "operation_not_supported",
                f"{operation or 'empty operation'} is not supported by {capability_id}",
            )
        arguments = payload.get("arguments")
        if not isinstance(arguments, Mapping):
            raise CapabilityBusinessError("invalid_input", "arguments must be an object")
        if operation == "change_logs.search":
            return self._search_change_logs(arguments, _context)
        if operation.startswith("collaboration.sessions."):
            return self._collaboration(operation, arguments, _context)
        if operation.startswith("share_links."):
            return self._share_link(operation, arguments, _context)
        if operation.startswith("permission_requests."):
            return self._permission_request(operation, arguments, _context)
        if operation.startswith("shares."):
            return self._direct_share(operation, arguments, _context)
        if operation.startswith("lists."):
            return self._list(operation, arguments, _context)
        if operation.startswith("projects."):
            return self._project(operation, arguments, _context)
        if operation.startswith("members."):
            return self._project(operation, arguments, _context)
        if operation.startswith("vehicle_models."):
            return self._vehicle_model(operation, arguments, _context)
        if operation.startswith("task_templates."):
            return self._task_template(operation, arguments, _context)
        if operation.startswith("approval."):
            return self._approval(operation, arguments, _context)
        if operation.startswith("workbenches."):
            return self._workbench(operation, arguments, _context)
        if operation.startswith("annotations."):
            key = _required_text(arguments, "key")
            if operation == "annotations.get": return {"data": self._repository.get_annotation(key)}
            self._repository.put_annotation(key, arguments.get("data")); return {"success": True}
        if operation.startswith("follows."):
            return self._follow(operation, arguments, _context)
        if operation.startswith("notifications."):
            return self._notification(operation, arguments, _context)
        if operation.startswith(("tasks.", "issues.", "task_dependencies.")):
            return self._work_item(operation, arguments, _context)
        item_type = _required_text(arguments, "item_type")
        item_gid = _required_text(arguments, "item_gid")
        if operation == "item_entries.get":
            rows = self._repository.list_item_entries(item_type, item_gid)
            return {"entries": [_entry(row) for row in rows]}
        if operation == "item_entries.delete":
            self._repository.delete_item_entries(item_type, item_gid)
            return {"success": True}

        entries = arguments.get("entries")
        if not isinstance(entries, list):
            raise CapabilityBusinessError("invalid_input", "entries must be an array")
        saved = [
            {**dict(entry), "gid": str(entry.get("gid") or self._next_id())}
            for entry in entries
            if isinstance(entry, Mapping)
        ]
        if len(saved) != len(entries):
            raise CapabilityBusinessError("invalid_input", "every entry must be an object")
        self._repository.replace_item_entries(item_type, item_gid, saved)
        return {"success": True, "count": len(saved), "entries": saved}

    def reject_order(self, command: RejectOrder, context: object) -> dict[str, Any]:
        actor_gid = str(getattr(context, "user_gid", "") or "")
        team_gid = str(getattr(context, "team_gid", "") or "")
        confirmation = str(getattr(context, "confirmation_token", "") or "")
        idempotency_key = str(
            getattr(context, "idempotency_key", "") or getattr(context, "operation_id", "") or ""
        )
        if not actor_gid or not team_gid:
            raise CapabilityBusinessError("unauthenticated", "actor and team scope are required")
        if not confirmation:
            raise CapabilityBusinessError("confirmation_required", "approval rejection requires confirmation")
        if not idempotency_key:
            raise CapabilityBusinessError("idempotency_required", "idempotency key is required")
        with self._repository.transaction() as transaction:
            replay = transaction.claim_approval_rejection(
                actor_gid=actor_gid,
                team_gid=team_gid,
                idempotency_key=idempotency_key,
                payload_hash=command.payload_hash(),
            )
            if replay is not None:
                return rejection_result_from_canonical(replay)
            order = transaction.require_rejectable_approval_order(
                order_gid=command.order_gid, actor_gid=actor_gid, team_gid=team_gid,
            )
            order = transaction.reject_approval_order(
                order=order,
                comment=command.comment,
                expected_revision=command.expected_revision,
            )
            notification_event_gid = self._next_id()
            transaction.enqueue_approval_rejection_notification(
                event_gid=notification_event_gid, order=order, team_gid=team_gid,
            )
            result = {
                "order_gid": command.order_gid,
                "status": "rejected",
                "revision": int(order["revision"]),
                "notification_event_gid": notification_event_gid,
            }
            canonical_result = canonical_rejection_result(result)
            transaction.complete_approval_rejection(
                actor_gid=actor_gid, team_gid=team_gid,
                idempotency_key=idempotency_key, canonical_result=canonical_result,
            )
            transaction.audit_approval_rejection(
                event_gid=self._next_id(), order_gid=command.order_gid,
                actor_gid=actor_gid, team_gid=team_gid, idempotency_key=idempotency_key,
                revision=result["revision"],
            )
            return rejection_result_from_canonical(canonical_result)

    def _list(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if not user_gid:
            raise CapabilityBusinessError("unauthenticated", "user identity is required")
        roles = frozenset(getattr(context, "active_roles", ()) or ())
        if operation == "lists.search":
            scope = arguments.get("scope")
            if not isinstance(scope, Mapping) or str(scope.get("user_gid") or "") != user_gid:
                raise CapabilityBusinessError("invalid_input", "server-derived scope is required")
            owner_team_gid = str(arguments.get("owner_team_gid") or "").strip() or None
            team_gids = [str(value) for value in scope.get("team_gids", [])]
            if owner_team_gid and owner_team_gid not in team_gids and not bool(scope.get("is_admin")):
                raise CapabilityBusinessError("forbidden", "team list access denied")
            rows = self._repository.search_lists(
                {"item_type": str(arguments.get("item_type") or "").strip() or None,
                 "owner_team_gid": owner_team_gid,
                 "q": str(arguments.get("q") or "").strip() or None},
                dict(scope),
            )
            return {"success": True, "data": [_project_list(row) for row in rows]}
        if operation == "lists.create":
            name = _required_text(arguments, "name")
            owner_type = str(arguments.get("owner_type") or "user")
            visibility = str(arguments.get("visibility") or "team")
            values = {
                "name": name, "color": str(arguments.get("color") or "#5b8dee"),
                "storage_scope": str(arguments.get("storage_scope") or "cloud"),
                "owner_type": owner_type,
                "owner_gid": user_gid if owner_type == "user" else _required_text(arguments, "owner_gid"),
                "creator_gid": user_gid, "visibility": visibility,
                "read_scope": str(arguments.get("read_scope") or _visibility_to_read_scope(visibility)),
                "write_scope": str(arguments.get("write_scope") or _visibility_to_write_scope(visibility)),
                "item_type": str(arguments.get("item_type") or "task"),
                "sort_order": int(arguments.get("sort_order") or 0),
            }
            gid = self._next_id(); self._repository.create_list(gid, values)
            return {"success": True, "data": {"gid": gid}}
        gid = _required_text(arguments, "gid")
        row = self._repository.get_list(gid)
        if row is None:
            raise CapabilityBusinessError("not_found", "list not found")
        is_admin = bool(roles & {"super_admin", "team_admin"})
        owner_only = str(row.get("owner_gid") or "") != user_gid and (row.get("owner_type") == "user" or not is_admin)
        update_source = arguments.get("updates") if isinstance(arguments.get("updates"), Mapping) else arguments
        if operation in {"lists.delete", "lists.retarget"} or "owner_gid" in update_source:
            if owner_only:
                raise CapabilityBusinessError("forbidden", "only the list owner or administrator can operate")
        if operation == "lists.delete":
            self._repository.archive_list(gid); return {"success": True}
        if operation == "lists.retarget":
            self._repository.retarget_list_items(gid, _required_text(arguments, "new_list_gid"), str(arguments.get("item_type") or ""))
            return {"success": True}
        allowed = {"name", "color", "sort_order", "owner_gid", "visibility", "read_scope", "write_scope", "project_gid", "shared_team_gid"}
        updates = {key: value for key, value in update_source.items() if key in allowed and value is not None}
        if update_source.get("project_gid") == "": updates["project_gid"] = None
        if "visibility" in updates:
            updates.setdefault("read_scope", _visibility_to_read_scope(str(updates["visibility"])))
            updates.setdefault("write_scope", _visibility_to_write_scope(str(updates["visibility"])))
        if not updates:
            raise CapabilityBusinessError("invalid_input", "no update fields")
        self._repository.update_list(gid, updates)
        return {"success": True}

    def _approval(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if operation == "approval.orders.search":
            scope = arguments.get("scope")
            if not isinstance(scope, Mapping) or str(scope.get("user_gid") or "") != user_gid: raise CapabilityBusinessError("invalid_input", "server-derived scope is required")
            return {"success": True, "data": self._repository.search_approval_orders({"status": str(arguments.get("status") or "") or None, "project_gid": str(arguments.get("project_gid") or "") or None}, dict(scope))}
        if operation == "approval.orders.create":
            gid = self._next_id(); self._repository.create_approval_order(gid, {"title": _required_text(arguments, "title"), "order_type": str(arguments.get("order_type") or "general"), "project_gid": arguments.get("project_gid"), "team_gid": getattr(context, "team_gid", None), "applicant_gid": user_gid, "reviewer_gid": arguments.get("reviewer_gid"), "source_ref": arguments.get("source_ref"), "content": dict(arguments.get("content") or {})})
            return {"success": True, "data": {"gid": gid}}
        if operation == "approval.scope_upgrade.create":
            current_scope = _required_text(arguments, "current_scope"); target_scope = _required_text(arguments, "target_scope"); order = ["local", "project", "team", "global"]
            if target_scope not in order or current_scope not in order or order.index(target_scope) <= order.index(current_scope): raise CapabilityBusinessError("invalid_input", "target scope must be higher than current scope")
            content = {key: arguments.get(key) for key in ("item_type", "item_gid", "item_title", "current_scope", "target_scope", "reason")}
            gid = self._next_id(); self._repository.create_approval_order(gid, {"title": f"范围提升申请：{content['item_title']}（{current_scope} → {target_scope}）", "order_type": "scope_upgrade", "project_gid": None, "team_gid": getattr(context, "team_gid", None), "applicant_gid": user_gid, "reviewer_gid": arguments.get("reviewer_gid"), "source_ref": None, "content": content})
            return {"success": True, "data": {"gid": gid, "reviewer_gid": arguments.get("reviewer_gid")}}
        gid = _required_text(arguments, "gid")
        if operation == "approval.orders.get":
            row = self._repository.get_approval_order(gid)
            if row is None: raise CapabilityBusinessError("not_found", "approval order not found")
            return {"success": True, "data": row}
        action = operation.rsplit(".", 1)[-1]
        row = self._repository.transition_approval_order(gid, action, user_gid, str(arguments.get("comment") or ("提交审批" if action == "start" else "已撤回" if action == "withdraw" else "")))
        if row is None: raise CapabilityBusinessError("invalid_state", "approval state or permission does not allow this action")
        if action == "approve" and row.get("order_type") == "scope_upgrade":
            content = row.get("content") or {}; self._repository.apply_scope_upgrade(str(content.get("item_type") or ""), str(content.get("item_gid") or ""), str(content.get("target_scope") or ""))
        result = {"success": True}
        if action in {"approve", "reject"}: result["notification"] = {"recipient_gid": row["applicant_gid"], "event": f"scope_{'approved' if action == 'approve' else 'rejected'}", "item_type": (row.get("content") or {}).get("item_type"), "item_gid": (row.get("content") or {}).get("item_gid")}
        return result

    def _workbench(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or ""); team_gid = str(getattr(context, "team_gid", "") or "") or None
        roles = frozenset(getattr(context, "active_roles", ()) or ())
        if operation == "workbenches.list":
            personal, teams, overrides = self._repository.list_workbenches(user_gid, team_gid)
            return {"success": True, "data": {"personal": [_workbench(row) for row in personal], "team": [_workbench(row, overrides.get((row["gid"], user_gid)) or overrides.get(row["gid"])) for row in teams]}}
        if operation == "workbenches.create":
            owner_type = str(arguments.get("owner_type") or "user")
            if owner_type == "team" and not roles & {"super_admin", "team_admin"}: raise CapabilityBusinessError("forbidden", "only team administrators can create team workbenches")
            owner_gid = _required_text(arguments, "owner_gid") if owner_type == "team" and arguments.get("owner_gid") else (team_gid if owner_type == "team" else user_gid)
            if not owner_gid: raise CapabilityBusinessError("invalid_input", "owner_gid is required")
            if self._repository.count_workbenches(owner_type, owner_gid) >= 3: raise CapabilityBusinessError("invalid_input", "at most three workbenches are allowed per owner")
            gid = self._next_id(); self._repository.create_workbench(gid, {"owner_type": owner_type, "owner_gid": owner_gid, "name": _required_text(arguments, "name"), "sort_order": int(arguments.get("sort_order") or 0), "widgets": list(arguments.get("widgets") or [])})
            return {"success": True, "data": {"gid": gid, "name": arguments["name"]}}
        gid = _required_text(arguments, "gid")
        if operation == "workbenches.overrides.get":
            row = self._repository.get_workbench_override(gid, user_gid)
            return {"success": True, "data": ({"widgets": row["widgets"] if isinstance(row.get("widgets"), list) else [], "updated_at": str(row["updated_at"])} if row else None)}
        if operation.startswith("workbenches.overrides."):
            workbench = self._repository.get_workbench(gid)
            if workbench is None: raise CapabilityBusinessError("not_found", "workbench not found")
            if operation.endswith("upsert"):
                if workbench["owner_type"] != "team": raise CapabilityBusinessError("invalid_input", "only team workbenches support member overrides")
                self._repository.upsert_workbench_override(gid, user_gid, list(arguments.get("widgets") or []))
            else: self._repository.delete_workbench_override(gid, user_gid)
            return {"success": True}
        row = self._repository.get_workbench(gid)
        if row is None: raise CapabilityBusinessError("not_found", "workbench not found")
        if row["owner_type"] == "user" and row["owner_gid"] != user_gid: raise CapabilityBusinessError("forbidden", "workbench access denied")
        if row["owner_type"] == "team" and not roles & {"super_admin", "team_admin"}: raise CapabilityBusinessError("forbidden", "only team administrators can modify team workbenches")
        if operation == "workbenches.delete": self._repository.delete_workbench(gid); return {"success": True}
        source = arguments.get("updates") if isinstance(arguments.get("updates"), Mapping) else arguments
        updates = {key: value for key, value in source.items() if key in {"name", "widgets", "sort_order"} and value is not None}
        if not updates: raise CapabilityBusinessError("invalid_input", "no update fields")
        self._repository.update_workbench(gid, updates); return {"success": True}

    def _follow(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        valid = {"any_change", "status_change", "comment_added", "resolved", "assigned_to_me", "mentioned"}
        if operation == "follows.list":
            rows = self._repository.list_follows(user_gid, str(arguments.get("item_type") or "") or None)
            return {"success": True, "data": [{**row, "notify_on": _notify_conditions(row.get("notify_on"), valid), "created_at": str(row["created_at"])} for row in rows]}
        if operation == "follows.check":
            row = self._repository.get_follow(user_gid, _required_text(arguments, "item_type"), _required_text(arguments, "item_gid"))
            return {"success": True, "data": ({"followed": True, "gid": row["gid"], "notify_on": _notify_conditions(row.get("notify_on"), valid)} if row else {"followed": False})}
        if operation == "follows.create":
            conditions = [str(value) for value in arguments.get("notify_on", ["status_change", "resolved"]) if str(value) in valid]
            gid = self._next_id()
            if not self._repository.create_follow(gid, {"user_gid": user_gid, "item_type": _required_text(arguments, "item_type"), "item_gid": _required_text(arguments, "item_gid"), "item_title": str(arguments.get("item_title") or ""), "notify_on": conditions}):
                raise CapabilityBusinessError("already_exists", "item is already followed")
            result = {"success": True, "data": {"gid": gid}}
            owner_gid = str(arguments.get("owner_gid") or "")
            if owner_gid and owner_gid != user_gid: result["notification"] = {"recipient_gid": owner_gid, "event": "new_follower", "item_type": arguments["item_type"], "item_gid": arguments["item_gid"]}
            return result
        gid = _required_text(arguments, "gid")
        if operation == "follows.delete":
            if not self._repository.delete_follow(gid, user_gid): raise CapabilityBusinessError("not_found", "follow not found")
            return {"success": True}
        conditions = [str(value) for value in arguments.get("notify_on", []) if str(value) in valid]
        if not self._repository.update_follow(gid, user_gid, conditions): raise CapabilityBusinessError("not_found", "follow not found")
        return {"success": True, "data": {"notify_on": conditions}}

    def _notification(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if operation == "notifications.list":
            rows = self._repository.list_notifications(user_gid, bool(arguments.get("unread_only")))
            return {"success": True, "data": [{"gid": row["gid"], "type": row.get("type") or "", "item_type": row.get("item_type") or "", "item_gid": row.get("item_gid") or "", "title": row.get("title") or "", "body": row.get("body") or "", "is_read": bool(row.get("is_read")), "created_at": str(row.get("created_at") or "")} for row in rows]}
        if operation == "notifications.unread_count": return {"success": True, "data": {"count": self._repository.count_unread_notifications(user_gid)}}
        if operation == "notifications.create":
            gid = self._next_id(); self._repository.create_notification(gid, {"user_gid": _required_text(arguments, "recipient_gid"), "type": _required_text(arguments, "type"), "item_type": arguments.get("item_type"), "item_gid": arguments.get("item_gid"), "title": _required_text(arguments, "title"), "body": str(arguments.get("body") or "")})
            return {"success": True, "data": {"gid": gid}}
        if operation == "notifications.mark_all_read": self._repository.mark_all_notifications_read(user_gid); return {"success": True}
        self._repository.mark_notification_read(_required_text(arguments, "gid"), user_gid); return {"success": True}

    def _work_item(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if operation.startswith("task_dependencies."):
            if operation == "task_dependencies.list": return {"success": True, "data": self._repository.list_task_dependencies(_required_text(arguments, "list_gid"))}
            if operation == "task_dependencies.create":
                gid = self._next_id(); row = self._repository.create_task_dependency(gid, {"source_gid": _required_text(arguments, "source_gid"), "target_gid": _required_text(arguments, "target_gid"), "edge_type": str(arguments.get("edge_type") or "prerequisite"), "dep_condition": str(arguments.get("dep_condition") or "done"), "dep_group": arguments.get("dep_group"), "label": str(arguments.get("label") or "")})
                return {"success": True, "data": row}
            gid = _required_text(arguments, "gid")
            if operation == "task_dependencies.delete": self._repository.delete_task_dependency(gid); return {"success": True}
            source = arguments.get("updates") if isinstance(arguments.get("updates"), Mapping) else arguments
            updates = {key: value for key, value in source.items() if key in {"edge_type", "dep_condition", "dep_group", "label"}}
            if not updates: raise CapabilityBusinessError("invalid_input", "no update fields")
            if not self._repository.update_task_dependency(gid, updates): raise CapabilityBusinessError("not_found", "dependency not found")
            return {"success": True}
        item_type = "task" if operation.startswith("tasks.") else "issue"
        if operation.endswith("search"):
            scope = arguments.get("scope")
            if not isinstance(scope, Mapping) or str(scope.get("user_gid") or "") != user_gid: raise CapabilityBusinessError("invalid_input", "server-derived scope is required")
            filters = {key: arguments.get(key) for key in ("project_gid", "status", "list_gid", "scheduled_date_from", "q", "page_size")}
            return {"success": True, "data": [_work_item_output(item_type, row) for row in self._repository.search_work_items(item_type, filters, dict(scope))]}
        if operation.endswith("get"):
            row = self._repository.get_work_item(item_type, _required_text(arguments, "gid"))
            if row is None: raise CapabilityBusinessError("not_found", f"{item_type} not found")
            return {"success": True, "data": _work_item_output(item_type, row)}
        if operation.endswith(("create", "promote")):
            gid = self._next_id(); prefix, sequence = (("T-C", "proj_tasks_display_seq") if item_type == "task" else ("I-C", "proj_issues_display_seq"))
            values = _work_item_values(item_type, arguments, user_gid, f"{prefix}{self._next_display_id(sequence):08d}")
            row = self._repository.create_work_item(item_type, gid, values)
            if operation.endswith("promote"): return {"success": True, "data": {"cloud_gid": gid, "local_gid": arguments.get("local_gid")}}
            return {"success": True, "data": _work_item_output(item_type, row)}
        gid = _required_text(arguments, "gid")
        if operation.endswith("delete"):
            if not self._repository.delete_work_item(item_type, gid, user_gid): raise CapabilityBusinessError("not_found", f"{item_type} not found or access denied")
            return {"success": True}
        source = arguments.get("updates") if isinstance(arguments.get("updates"), Mapping) else arguments
        allowed = _TASK_UPDATE_FIELDS if item_type == "task" else _ISSUE_UPDATE_FIELDS
        updates = {key: value for key, value in source.items() if key in allowed}
        if not updates: raise CapabilityBusinessError("invalid_input", "no update fields")
        row = self._repository.get_work_item(item_type, gid)
        roles = frozenset(getattr(context, "active_roles", ()) or ())
        if "attachments" in updates and row and str(row.get("owner_user_gid") or "") != user_gid and not roles & {"super_admin", "team_admin"}: raise CapabilityBusinessError("forbidden", "only owner or administrator can edit attachments")
        events = ["any_change"]
        if "status" in updates:
            events.append("status_change")
            if str(updates["status"]).lower() in {"done", "resolved", "closed", "completed"}: events.append("resolved")
        if "assignee_team_gid" in updates: events.append("assigned_to_me")
        if not self._repository.update_work_item(item_type, gid, updates, user_gid, events): raise CapabilityBusinessError("not_found", f"{item_type} not found")
        return {"success": True}

    def _project(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        team_gid = str(getattr(context, "team_gid", "") or "")
        if not user_gid:
            raise CapabilityBusinessError("unauthenticated", "user identity is required")
        if operation.startswith("members."):
            from backend.platform_sdk.project_access import (
                add_project_member,
                can_manage_project,
                list_all_project_memberships,
                remove_project_member,
                replace_project_manager,
                replace_section_leads,
            )
            from backend.platform_sdk.craft_project_scope import equivalent_line_gids
            project_gid = _required_text(arguments, "project_gid")
            if operation == "members.list":
                rows = [row for row in list_all_project_memberships() if str(row.get("project_gid") or "") == project_gid]
                return {"success": True, "data": rows}
            if operation == "members.line_assignment.replace":
                if "super_admin" not in set(getattr(context, "active_roles", ()) or ()) and not can_manage_project(user_gid, project_gid):
                    raise CapabilityBusinessError("forbidden", "caller cannot manage project line assignments")
                line_gid = str(arguments.get("line_gid") or "").strip()
                target_user_gid = str(arguments.get("user_gid") or "").strip() or None
                if line_gid:
                    line_gids = equivalent_line_gids(project_gid, line_gid)
                    if not line_gids:
                        raise CapabilityBusinessError("not_found", "line not found")
                    replace_section_leads(project_gid, line_gids, target_user_gid, user_gid)
                else:
                    replace_project_manager(project_gid, target_user_gid)
                return {"success": True}
            if operation == "members.add":
                member_gid = add_project_member(project_gid, _required_text(arguments, "user_gid"), str(arguments.get("project_role") or "member"), arguments.get("section_gid"))
                return {"success": True, "data": {"gid": member_gid}}
            if not remove_project_member(project_gid, _required_text(arguments, "member_gid")):
                raise CapabilityBusinessError("not_found", "member not found")
            return {"success": True}
        if operation == "projects.search":
            scope = arguments.get("scope")
            if not isinstance(scope, Mapping) or str(scope.get("user_gid") or "") != user_gid:
                raise CapabilityBusinessError("invalid_input", "server-derived scope is required")
            rows = self._repository.search_projects(
                {"include_deleted": bool(arguments.get("include_deleted")), "include_archived": bool(arguments.get("include_archived"))}, dict(scope)
            )
            return {"success": True, "data": [_project(row) for row in rows]}
        if operation == "projects.create":
            code = _required_text(arguments, "project_code")
            year = arguments.get("model_year")
            if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2099):
                raise CapabilityBusinessError("invalid_input", "model_year must be between 2000 and 2099")
            suffix = str(arguments.get("suffix") or "").strip()
            name = _project_name(code, year, suffix); gid = self._next_id()
            self._repository.create_project(gid, {
                "name": name, "project_code": code, "model_year": year, "suffix": suffix,
                "description": str(arguments.get("description") or ""), "status": str(arguments.get("status") or "preparing"),
                "vehicle_model_gid": arguments.get("vehicle_model_gid"), "factory_gid": arguments.get("factory_gid"),
                "team_id": str(arguments.get("team_id") or team_gid), "owner_gid": user_gid,
                "jph": arguments.get("jph"), "share_scope": "team",
            })
            return {"success": True, "data": {"gid": gid, "name": name}}
        gid = _required_text(arguments, "gid")
        row = self._repository.get_project(gid)
        if row is None:
            raise CapabilityBusinessError("not_found", "project not found")
        if operation == "projects.get":
            result = _project(row); result["meta"] = row.get("meta"); return {"success": True, "data": result}
        if operation == "projects.delete":
            self._repository.delete_project(gid); return {"success": True}
        source = arguments.get("updates")
        if not isinstance(source, Mapping):
            raise CapabilityBusinessError("invalid_input", "updates must be an object")
        allowed = {"project_code", "model_year", "suffix", "description", "status", "vehicle_model_gid", "owner_gid", "jph", "is_archived", "factory_gid"}
        updates = {key: value for key, value in source.items() if key in allowed and value is not None}
        if not updates:
            raise CapabilityBusinessError("invalid_input", "no update fields")
        year = updates.get("model_year")
        if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2099):
            raise CapabilityBusinessError("invalid_input", "model_year must be between 2000 and 2099")
        if {"project_code", "model_year", "suffix"} & updates.keys():
            updates["name"] = _project_name(str(updates.get("project_code", row.get("project_code") or "")).strip(), updates.get("model_year", row.get("model_year")), str(updates.get("suffix", row.get("suffix") or "")).strip())
        self._repository.update_project(gid, updates); return {"success": True}

    def _vehicle_model(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        if operation == "vehicle_models.list":
            return {"success": True, "data": [{**row, "created_at": str(row["created_at"]), "vehicle_type": row.get("vehicle_type") or ""} for row in self._repository.list_vehicle_models()]}
        if operation == "vehicle_models.create":
            gid = self._next_id(); values = {
                "name": _required_text(arguments, "name"), "brand": str(arguments.get("brand") or ""),
                "platform": str(arguments.get("platform") or ""), "vehicle_type": str(arguments.get("vehicle_type") or ""),
                "team_id": str(arguments.get("team_id") or getattr(context, "team_gid", "") or ""),
            }
            self._repository.create_vehicle_model(gid, values); return {"success": True, "data": {"gid": gid, "name": values["name"]}}
        gid = _required_text(arguments, "gid")
        if operation == "vehicle_models.delete":
            if not self._repository.delete_vehicle_model(gid): raise CapabilityBusinessError("not_found", "vehicle model not found")
            return {"success": True}
        values = {key: str(arguments.get(key) or "") for key in ("name", "brand", "platform", "vehicle_type")}
        if not values["name"]: raise CapabilityBusinessError("invalid_input", "name is required")
        if not self._repository.update_vehicle_model(gid, values): raise CapabilityBusinessError("not_found", "vehicle model not found")
        return {"success": True}

    def _task_template(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if operation == "task_templates.list":
            return {"success": True, "data": self._repository.list_task_templates()}
        if operation == "task_templates.create":
            gid = self._next_id(); self._repository.create_task_template(gid, {"name": _required_text(arguments, "name"), "description": str(arguments.get("description") or ""), "scope": str(arguments.get("scope") or "system"), "owner_gid": user_gid})
            return {"success": True, "data": {"gid": gid}}
        if operation == "task_templates.get":
            row = self._repository.get_task_template(_required_text(arguments, "gid"))
            if row is None: raise CapabilityBusinessError("not_found", "task template not found")
            return {"success": True, "data": row}
        if operation == "task_templates.items.create":
            gid = self._next_id(); self._repository.create_task_template_item(gid, {"template_gid": _required_text(arguments, "template_gid"), **_template_item_values(arguments)})
            return {"success": True, "data": {"gid": gid}}
        if operation == "task_templates.instantiate":
            gid = _required_text(arguments, "gid"); template = self._repository.get_task_template(gid)
            if template is None or not template.get("is_active", True): raise CapabilityBusinessError("not_found", "task template not found or inactive")
            start_date = _required_text(arguments, "start_date"); title_vars = arguments.get("title_vars") if isinstance(arguments.get("title_vars"), Mapping) else {}
            assignee_map = arguments.get("assignee_map") if isinstance(arguments.get("assignee_map"), Mapping) else {}
            created = []
            for item in template.get("items", []):
                task_gid = self._next_id(); role = item.get("assignee_role")
                due = None if item.get("due_offset_days") is None else (date.fromisoformat(start_date) + timedelta(days=int(item["due_offset_days"]))).isoformat()
                title = re.sub(r"\{\{(.+?)\}\}", lambda match: str(title_vars.get(match.group(1).strip(), match.group(0))), item["title_pattern"])
                assignee = assignee_map.get(role) if role else None
                created.append({"gid": task_gid, "title": title, "due_date": due, "assignee_gid": assignee, "template_item_gid": item["gid"]})
            self._repository.create_tasks_from_template([{**row, "description": next(item.get("description", "") for item in template["items"] if item["gid"] == row["template_item_gid"]), "owner_user_gid": str(arguments.get("owner_user_gid") or user_gid), "project_gid": _required_text(arguments, "project_gid"), "priority": next(item.get("priority", "normal") for item in template["items"] if item["gid"] == row["template_item_gid"]), "share_scope": next(item.get("share_scope", "team") for item in template["items"] if item["gid"] == row["template_item_gid"]), "template_source_version": template["version"]} for row in created])
            return {"success": True, "data": created, "count": len(created)}
        gid_key = "item_gid" if ".items." in operation else "gid"; gid = _required_text(arguments, gid_key)
        if operation.endswith("delete"):
            deleted = self._repository.delete_task_template_item(gid) if ".items." in operation else self._repository.delete_task_template(gid)
            if not deleted: raise CapabilityBusinessError("not_found", "task template resource not found")
            return {"success": True}
        source = arguments.get("updates") if isinstance(arguments.get("updates"), Mapping) else arguments
        updates = {key: value for key, value in source.items() if key in ({"title_pattern", "description", "priority", "assignee_role", "due_offset_days", "share_scope", "sort_order"} if ".items." in operation else {"name", "description", "scope", "is_active"}) and value is not None}
        if not updates: raise CapabilityBusinessError("invalid_input", "no update fields")
        updated = self._repository.update_task_template_item(gid, updates) if ".items." in operation else self._repository.update_task_template(gid, updates)
        if not updated: raise CapabilityBusinessError("not_found", "task template resource not found")
        return {"success": True}

    def _search_change_logs(
        self, arguments: Mapping[str, Any], context: object
    ) -> list[dict[str, Any]]:
        list_gid = str(arguments.get("list_gid") or "").strip()
        item_gid = str(arguments.get("item_gid") or "").strip()
        if not list_gid and not item_gid:
            raise CapabilityBusinessError(
                "invalid_input", "item_gid or list_gid is required"
            )
        limit = _bounded_int(
            arguments, "limit", default=100, minimum=1, maximum=500
        )
        offset = _bounded_int(
            arguments, "offset", default=0, minimum=0, maximum=1_000_000
        )
        user_gid = str(getattr(context, "user_gid", "") or "")
        active_roles = frozenset(getattr(context, "active_roles", ()) or ())
        can_read_all = "super_admin" in active_roles
        if list_gid:
            owner_gid = self._repository.get_list_owner(list_gid)
            if not can_read_all and owner_gid != user_gid:
                raise CapabilityBusinessError(
                    "forbidden", "only the list owner can read complete change history"
                )
            return self._repository.list_change_logs_by_list(list_gid, limit, offset)

        item_type = _required_text(arguments, "item_type")
        owner_gid = self._repository.get_item_list_owner(item_type, item_gid)
        changed_by = None if can_read_all or owner_gid == user_gid else user_gid
        return self._repository.list_change_logs_by_item(
            item_type, item_gid, changed_by, limit, offset
        )

    def _collaboration(
        self, operation: str, arguments: Mapping[str, Any], context: object
    ) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if not user_gid:
            raise CapabilityBusinessError("unauthenticated", "user identity is required")
        if operation == "collaboration.sessions.list":
            section_gid = str(arguments.get("section_gid") or "").strip() or None
            rows = self._repository.list_collaboration_sessions(section_gid)
            return {
                "success": True,
                "data": [_collaboration_session(row) for row in rows],
            }
        if operation == "collaboration.sessions.create":
            section_gid = _required_text(arguments, "section_gid")
            gid = self._next_id()
            self._repository.create_collaboration_session(gid, section_gid, user_gid)
            return {"success": True, "data": {"gid": gid}}

        gid = _required_text(arguments, "gid")
        if operation == "collaboration.sessions.get":
            row = self._repository.get_collaboration_session(gid)
            if row is None:
                raise CapabilityBusinessError("not_found", "collaboration session not found")
            return {
                "success": True,
                "data": _collaboration_session(row, include_meta=True),
            }
        if operation == "collaboration.sessions.join":
            self._repository.join_collaboration_session(gid, user_gid)
            return {"success": True}
        if not self._repository.end_collaboration_session(gid, user_gid):
            raise CapabilityBusinessError(
                "forbidden", "only the session owner can end this session"
            )
        return {"success": True}

    def _share_link(
        self, operation: str, arguments: Mapping[str, Any], context: object
    ) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if not user_gid:
            raise CapabilityBusinessError("unauthenticated", "user identity is required")
        if operation == "share_links.create":
            target_type = _required_text(arguments, "target_type")
            target_gid = _required_text(arguments, "target_gid")
            token = self._next_token()
            row = self._repository.create_share_link(
                token,
                {
                    "target_type": target_type,
                    "target_gid": target_gid,
                    "item_type": arguments.get("item_type"),
                    "display_name": str(arguments.get("display_name") or ""),
                    "created_by": user_gid,
                    "expires_at": arguments.get("expires_at"),
                },
            )
            return {"token": token, "link": row}
        token = _required_text(arguments, "token")
        if operation == "share_links.resolve":
            link = self._repository.resolve_share_link(token)
            if link is None:
                raise CapabilityBusinessError("not_found", "share link not found or expired")
            current_permission = "none"
            can_request = False
            if link["target_type"] == "list":
                current_permission = self._repository.get_list_access(
                    str(link["target_gid"]), user_gid, getattr(context, "team_gid", None)
                )
                can_request = current_permission == "none"
            return {
                "target_type": link["target_type"],
                "target_gid": link["target_gid"],
                "item_type": link.get("item_type"),
                "display_name": link["display_name"],
                "current_permission": current_permission,
                "can_request": can_request,
            }
        is_super = "super_admin" in frozenset(getattr(context, "active_roles", ()) or ())
        result = self._repository.delete_share_link(token, user_gid, is_super)
        if result == "not_found":
            raise CapabilityBusinessError("not_found", "share link not found")
        if result == "forbidden":
            raise CapabilityBusinessError("forbidden", "only the creator can revoke this link")
        return {"ok": True}

    def _direct_share(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if operation.startswith("shares.list."):
            list_gid = _required_text(arguments, "list_gid")
            if not self._repository.is_list_owner(list_gid, user_gid):
                raise CapabilityBusinessError("forbidden", "only the list owner can manage shares")
            if operation == "shares.list.list":
                return {"shares": self._repository.list_list_shares(list_gid)}
            if operation == "shares.list.delete":
                self._repository.delete_list_share(list_gid, _required_text(arguments, "gid")); return {"ok": True}
            row = self._repository.upsert_list_share(self._next_id(), {"list_gid": list_gid, "shared_to": _required_text(arguments, "shared_to"), "permission": str(arguments.get("permission") or "read"), "shared_by": user_gid})
            return {"share": row}
        if operation == "shares.item.create":
            row = self._repository.upsert_item_share(self._next_id(), {"item_type": _required_text(arguments, "item_type"), "item_gid": _required_text(arguments, "item_gid"), "shared_to": _required_text(arguments, "shared_to"), "permission": str(arguments.get("permission") or "read"), "shared_by": user_gid})
            return {"share": row}
        result = self._repository.delete_item_share(_required_text(arguments, "gid"), user_gid)
        if result != "deleted":
            raise CapabilityBusinessError(result, "share not found" if result == "not_found" else "only the share creator can revoke it")
        return {"ok": True}

    def _permission_request(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        if operation == "permission_requests.list":
            rows = self._repository.list_permission_requests(
                str(arguments.get("target_gid") or "").strip() or None,
                str(arguments.get("status") or "").strip() or None,
            )
            return {"requests": rows}
        if operation == "permission_requests.create":
            row = self._repository.create_permission_request(self._next_id(), {
                "requester_gid": user_gid,
                "target_type": _required_text(arguments, "target_type"),
                "target_gid": _required_text(arguments, "target_gid"),
                "want_permission": str(arguments.get("want_permission") or "read"),
                "message": str(arguments.get("message") or ""),
            })
            return {"request": row}
        gid = _required_text(arguments, "gid")
        decision = "approved" if operation.endswith("approve") else "rejected"
        result, row = self._repository.decide_permission_request(gid, user_gid, decision)
        if result == "not_found":
            raise CapabilityBusinessError("not_found", "permission request not found")
        if result == "already_decided":
            raise CapabilityBusinessError("already_decided", "permission request already decided")
        assert row is not None
        return {"ok": True, "notification": {
            "recipient_gid": row["requester_gid"], "event": f"permission_{decision}",
            "target_type": row["target_type"], "target_gid": row["target_gid"],
        }}


__all__ = ["APPROVAL_REJECT_CAPABILITY_ID", "APPROVAL_REJECT_CAPABILITY_VERSION", "ItemEntryRepository", "ProjectManagementApplication", "RejectOrder", "canonical_rejection_result", "rejection_result_from_canonical"]
