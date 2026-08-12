"""Project Management application service and operation dispatch."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol
from uuid import uuid4
import secrets
import re
from datetime import date, timedelta

from backend.capability_v2.provider_contracts import CapabilityBusinessError


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
    "project.task_template.read": frozenset({"task_templates.list", "task_templates.get"}),
    "project.task_template.change.apply": frozenset({"task_templates.create", "task_templates.update", "task_templates.delete", "task_templates.items.create", "task_templates.items.update", "task_templates.items.delete", "task_templates.instantiate"}),
}


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


class ProjectManagementApplication:
    def __init__(
        self,
        repository: ItemEntryRepository,
        *,
        next_id: Callable[[], str] | None = None,
        next_token: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._next_id = next_id or (lambda: str(uuid4()))
        self._next_token = next_token or (lambda: secrets.token_urlsafe(16))

    def invoke(
        self,
        capability_id: str,
        payload: dict[str, Any],
        _context: object,
    ) -> Any:
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
        if operation.startswith("vehicle_models."):
            return self._vehicle_model(operation, arguments, _context)
        if operation.startswith("task_templates."):
            return self._task_template(operation, arguments, _context)
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

    def _project(self, operation: str, arguments: Mapping[str, Any], context: object) -> dict[str, Any]:
        user_gid = str(getattr(context, "user_gid", "") or "")
        team_gid = str(getattr(context, "team_gid", "") or "")
        if not user_gid:
            raise CapabilityBusinessError("unauthenticated", "user identity is required")
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


__all__ = ["ItemEntryRepository", "ProjectManagementApplication"]
